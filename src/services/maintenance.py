"""Credit-safe, idempotent maintenance for provider snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.competitions import collection_for, competition_document_id, find_competition_document, get_competition
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
        cache_collection.update_one(
            {"_id": lease_id, "lease_until": existing.get("lease_until")},
            {"$set": {key: value for key, value in lease.items() if key != "_id"}},
            upsert=False,
        )

    try:
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
            return {"status": "idle", "provider_calls": 0, "mutated": False, "buckets": []}

        try:
            quotes = _bulk_quotes(odds_provider, comp)
        except Exception as exc:
            for event_id, (fixture, due) in due_by_event.items():
                for bucket in due[:-1]:
                    mark_bucket(cache_collection, comp, event_id, bucket, status="unavailable", error="missed")
                mark_bucket(cache_collection, comp, event_id, due[-1], status="failed", error=str(exc))
            return {
                "status": "failed",
                "error": str(exc),
                "provider_calls": 1,
                "mutated": True,
                "buckets": sorted(set(all_due), key=lambda item: list(_bucket_order()).index(item)),
            }

        lookup = _quote_lookup(quotes)
        for event_id, (fixture, due) in due_by_event.items():
            # Missing historical windows become explicit missed buckets; only
            # the current (closest-to-kickoff) observation is recorded.
            for bucket in due[:-1]:
                mark_bucket(cache_collection, comp, event_id, bucket, status="unavailable", error="missed")
            match = lookup.get(event_id) or _match_by_names(lookup, fixture)
            observed_bucket = due[-1]
            if match is None:
                append_odds_snapshot(
                    cache_collection, comp, event_id, observed_bucket, current, {}, status="unavailable",
                    error="event not returned by odds provider",
                )
                mark_bucket(cache_collection, comp, event_id, observed_bucket, status="unavailable", observed_at=current, error="event not returned by odds provider")
            else:
                odds = match.get("odds") or _extract_odds(match)
                snapshot_status = "fresh" if odds else "unavailable"
                append_odds_snapshot(cache_collection, comp, event_id, observed_bucket, current, odds, status=snapshot_status)
                mark_bucket(cache_collection, comp, event_id, observed_bucket, status="fresh" if odds else "unavailable", observed_at=current)
        return {
            "status": "success",
            "provider_calls": 1,
            "mutated": True,
            "buckets": sorted(set(all_due), key=lambda item: list(_bucket_order()).index(item)),
            "events": len(due_by_event),
        }
    finally:
        cache_collection.delete_one({"_id": lease_id, "lease_token": lease_token})


def _fixtures(cache_collection, competition) -> list[dict]:
    document = find_competition_document(cache_collection, competition, "matches_cache") or {}
    return document.get("data") or []


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
        if quote.get("home_team") == home and quote.get("away_team") == away:
            return quote
    return None


def _extract_odds(quote):
    if quote.get("odds"):
        return quote["odds"]
    # Keep provider payloads intact when no normalized odds are supplied; the
    # next prediction layer can normalize bookmaker markets later.
    bookmakers = quote.get("bookmakers", [])
    return {"bookmakers": bookmakers} if bookmakers else {}


def _bucket_order():
    return ("t24h", "t6h", "t75m", "t30m", "t15m")
