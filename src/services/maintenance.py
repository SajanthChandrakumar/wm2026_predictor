"""Credit-safe, idempotent maintenance for provider snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from uuid import uuid4

from src.competitions import collection_for, competition_document_id, find_competition_document, get_competition
from src.services.odds_helpers import extract_odds
from src.services.snapshots import append_odds_snapshot, bucket_state, due_buckets, mark_bucket, parse_time


LEASE_SECONDS = 300


def run_maintenance(
    cache_collections,
    odds_provider,
    *,
    competition=None,
    now=None,
    force: bool = False,
    lease_seconds: int = LEASE_SECONDS,
    fixture_fetcher=None,
    clubelo_ingestor=None,
) -> dict:
    """Capture due odds buckets with at most one bulk provider call.

    ``force`` is deliberately a public no-op.  Manual/public refreshes cannot
    spend provider credits or write a snapshot; only the authenticated route
    should invoke normal maintenance.
    """
    comp = get_competition(competition)
    if force:
        return {"status": "noop", "reason": "force_disabled", "provider_calls": 0, "mutated": False}
    cache_collection = collection_for(cache_collections, comp)
    current = parse_time(now or datetime.now(timezone.utc))
    lease_id = competition_document_id(comp, "maintenance_lease")
    lease_token = uuid4().hex
    lease = {
        "_id": lease_id,
        "competition": comp.id,
        "lease_until": (current + timedelta(seconds=lease_seconds)).isoformat(),
        "lease_token": lease_token,
    }
    try:
        cache_collection.insert_one(lease)
        owns_lease = True
    except Exception:
        # Unique _id is the Mongo claim. A live holder wins; a crashed worker's
        # expired claim can be atomically replaced using its old lease value.
        existing = cache_collection.find_one({"_id": lease_id}) or {}
        try:
            expiry = parse_time(existing.get("lease_until"))
        except (TypeError, ValueError):
            expiry = current
        if expiry > current:
            return {"status": "skipped", "reason": "lease_held", "provider_calls": 0, "mutated": False, "buckets": []}
        result = cache_collection.update_one(
            {"_id": lease_id, "lease_until": existing.get("lease_until")},
            {"$set": {key: value for key, value in lease.items() if key != "_id"}},
            upsert=False,
        )
        matched = getattr(result, "matched_count", None)
        if matched == 0:
            owns_lease = False
        elif matched is None:
            owns_lease = (cache_collection.find_one({"_id": lease_id}) or {}).get("lease_token") == lease_token
        else:
            owns_lease = True
    if not owns_lease:
        return {"status": "skipped", "reason": "lease_held", "provider_calls": 0, "mutated": False, "buckets": []}

    fixture_status = {"status": "fresh", "source": "cache", "observed_at": current.isoformat()}
    clubelo_status = None
    try:
        if fixture_fetcher is not None:
            fixture_status = _refresh_fixtures(cache_collection, comp, fixture_fetcher, current)
        if comp.id == "ucl2026" and clubelo_ingestor is not None:
            clubelo_status = clubelo_ingestor(cache_collection, competition=comp, observed_at=current)
        fixtures = _fixtures(cache_collection, comp)
        due_by_event = {}
        all_due = []
        for fixture in fixtures:
            event_id = str(fixture.get("id") or fixture.get("event_id") or "")
            kickoff = fixture.get("commence_time") or (fixture.get("raw_match") or {}).get("commence_time")
            if not event_id or not kickoff:
                continue
            due = due_buckets(kickoff, current, bucket_state(cache_collection, comp, event_id).keys())
            if due:
                due_by_event[event_id] = (fixture, due)
                all_due.extend(due)
        if not due_by_event:
            return {"status": "idle", "provider_calls": 0, "mutated": False, "buckets": [], "fixture_status": fixture_status, "clubelo_status": clubelo_status}

        try:
            quotes = _bulk_quotes(odds_provider, comp)
        except Exception as exc:
            for event_id, (fixture, due) in due_by_event.items():
                for bucket in due[:-1]:
                    mark_bucket(cache_collection, comp, event_id, bucket, status="unavailable", observed_at=current, error="missed")
                mark_bucket(cache_collection, comp, event_id, due[-1], status="failed", observed_at=current, error=str(exc))
            return {
                "status": "failed",
                "source": "odds_api",
                "observed_at": current.isoformat(),
                "error": str(exc),
                "provider_calls": 1,
                "mutated": True,
                "buckets": sorted(set(all_due), key=lambda item: list(_bucket_order()).index(item)),
                "fixture_status": fixture_status,
                "clubelo_status": clubelo_status,
            }

        lookup = _quote_lookup(quotes)
        for event_id, (fixture, due) in due_by_event.items():
            # Missing historical windows become explicit missed buckets; only
            # the current (closest-to-kickoff) observation is recorded.
            for bucket in due[:-1]:
                mark_bucket(cache_collection, comp, event_id, bucket, status="unavailable", observed_at=current, error="missed")
            match = lookup.get(event_id) or _match_by_names(lookup, fixture)
            observed_bucket = due[-1]
            if match is None:
                append_odds_snapshot(
                    cache_collection, comp, event_id, observed_bucket, current, {}, status="unavailable",
                    error="event not returned by odds provider",
                )
                mark_bucket(cache_collection, comp, event_id, observed_bucket, status="unavailable", observed_at=current, error="event not returned by odds provider")
            else:
                odds = _extract_odds(match)
                snapshot_status = "fresh" if odds else "unavailable"
                append_odds_snapshot(cache_collection, comp, event_id, observed_bucket, current, odds, status=snapshot_status)
                mark_bucket(cache_collection, comp, event_id, observed_bucket, status="fresh" if odds else "unavailable", observed_at=current)
                if odds:
                    _store_fixture_odds(cache_collection, comp, event_id, odds, match)
        return {
            "status": "success",
            "provider_calls": 1,
            "mutated": True,
            "buckets": sorted(set(all_due), key=lambda item: list(_bucket_order()).index(item)),
            "events": len(due_by_event),
            "fixture_status": fixture_status,
            "clubelo_status": clubelo_status,
        }
    finally:
        cache_collection.delete_one({"_id": lease_id, "lease_token": lease_token})


def _fixtures(cache_collection, competition) -> list[dict]:
    document = find_competition_document(cache_collection, competition, "matches_cache") or {}
    return document.get("data") or []


def _refresh_fixtures(cache_collection, competition, fetcher, current) -> dict:
    """Refresh the fixture skeleton without collecting paid enrichment."""
    comp = get_competition(competition)
    fetch_now = current
    days_back = 30
    days_forward = 75
    if comp.id == "ucl2026":
        start_year = int(comp.season.split("/", 1)[0])
        season_start = current.replace(year=start_year, month=7, day=1)
        season_end = current.replace(year=start_year + 1, month=6, day=30)
        fetch_now = min(max(current, season_start), season_end)
        days_back = (fetch_now.date() - season_start.date()).days
        days_forward = (season_end.date() - fetch_now.date()).days
    kwargs = {
        "competition": comp,
        "now": fetch_now,
        "days_back": days_back,
        "days_forward": days_forward,
        "chunk_days": 7,
    }
    try:
        fixtures = fetcher(**kwargs) or []
    except Exception as exc:
        return {"status": "failed", "source": "espn", "observed_at": current.isoformat(), "error": str(exc)}
    existing_document = find_competition_document(cache_collection, comp, "matches_cache") or {}
    existing = {
        str(item.get("id") or item.get("event_id")): dict(item)
        for item in existing_document.get("data", [])
        if isinstance(item, dict) and (item.get("id") or item.get("event_id"))
    }
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            continue
        event_id = str(fixture.get("id") or fixture.get("event_id") or "")
        if not event_id:
            continue
        match = dict(existing.get(event_id) or {})
        match.update({key: fixture.get(key) for key in (
            "id", "home_team", "away_team", "home_logo", "away_logo",
            "commence_time", "round", "completed", "actual_score",
        ) if key in fixture})
        raw_match = dict(match.get("raw_match") or {})
        raw_match.update({
            "id": event_id,
            "home_team": match.get("home_team"),
            "away_team": match.get("away_team"),
            "commence_time": match.get("commence_time"),
            "round": match.get("round", ""),
        })
        if match.get("bookmakers"):
            raw_match["bookmakers"] = match["bookmakers"]
        match["raw_match"] = raw_match
        match.setdefault("status", "unavailable")
        match.setdefault("source", "cache")
        existing[event_id] = match
    data = sorted(existing.values(), key=lambda item: item.get("commence_time", ""))
    cache_collection.update_one(
        {"_id": competition_document_id(comp, "matches_cache")},
        {"$set": {
            "competition": comp.id,
            "timestamp": current.timestamp(),
            "observed_at": current.isoformat(),
            "source": "espn",
            "status": "fresh",
            "data": data,
        }},
        upsert=True,
    )
    return {"status": "fresh", "source": "espn", "observed_at": current.isoformat(), "fixtures": len(data)}


def _bulk_quotes(provider, competition):
    if hasattr(provider, "get_competition_odds"):
        return provider.get_competition_odds(competition, market="h2h,totals") or []
    return provider.get_world_cup_odds(market="h2h,totals") or []


def _quote_lookup(quotes) -> dict:
    lookup = {}
    for quote in quotes or []:
        event_id = str(quote.get("id") or quote.get("event_id") or "")
        if event_id:
            lookup[event_id] = quote
    return lookup


def _match_by_names(lookup, fixture):
    home, away = fixture.get("home_team"), fixture.get("away_team")
    for quote in lookup.values():
        if _normalise_team(quote.get("home_team")) == _normalise_team(home) and _normalise_team(quote.get("away_team")) == _normalise_team(away):
            return quote
    return None


def _extract_odds(quote):
    direct = quote.get("odds")
    if isinstance(direct, dict):
        source = direct.get("odds") if isinstance(direct.get("odds"), dict) else direct
        try:
            values = {key: float(source[key]) for key in ("home", "draw", "away")}
            for key in ("over25", "under25"):
                if key in source:
                    values[key] = float(source[key])
            if any(not math.isfinite(value) or value <= 1.0 for value in values.values()):
                return {}
            return values
        except (KeyError, TypeError, ValueError):
            pass
    bookmakers = quote.get("bookmakers") or []
    if not bookmakers:
        return {}
    try:
        odds = extract_odds({
            "home_team": quote.get("home_team"),
            "away_team": quote.get("away_team"),
            "bookmakers": bookmakers,
        })
    except (TypeError, ValueError, KeyError):
        return {}
    return {key: float(value) for key, value in odds.items() if key in {"home", "draw", "away", "over25", "under25"}}


def _normalise_team(value):
    return " ".join(str(value or "").casefold().split())


def _store_fixture_odds(cache_collection, competition, event_id, odds, quote):
    comp = get_competition(competition)
    document = find_competition_document(cache_collection, comp, "matches_cache") or {}
    data = list(document.get("data") or [])
    for match in data:
        if str(match.get("id") or match.get("event_id")) != str(event_id):
            continue
        match["odds"] = odds
        if quote.get("bookmakers"):
            match["bookmakers"] = quote["bookmakers"]
            match.setdefault("raw_match", {})["bookmakers"] = quote["bookmakers"]
        match["status"] = "fresh"
        match["source_status"] = "fresh"
        match["source"] = "odds_api"
        break
    cache_collection.update_one(
        {"_id": competition_document_id(comp, "matches_cache")},
        {"$set": {"data": data}},
        upsert=True,
    )


def _bucket_order():
    return ("t24h", "t6h", "t75m", "t30m", "t15m")
