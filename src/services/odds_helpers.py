import time
import statistics
from datetime import datetime


def extract_odds(match):
    home_team = match.get("home_team")
    away_team = match.get("away_team")
    collected = {"home": [], "draw": [], "away": [], "over25": [], "under25": []}
    for bookie in match.get("bookmakers", []):
        for market in bookie.get("markets", []):
            if market["key"] == "h2h":
                for outcome in market.get("outcomes", []):
                    if outcome["name"] == home_team:
                        collected["home"].append(outcome["price"])
                    elif outcome["name"] == away_team:
                        collected["away"].append(outcome["price"])
                    elif outcome["name"] == "Draw":
                        collected["draw"].append(outcome["price"])
            elif market["key"] == "totals":
                for outcome in market.get("outcomes", []):
                    if outcome.get("point") == 2.5:
                        if outcome["name"] == "Over":
                            collected["over25"].append(outcome["price"])
                        elif outcome["name"] == "Under":
                            collected["under25"].append(outcome["price"])
    odds = {k: statistics.median(v) for k, v in collected.items() if v}
    required_keys = ["home", "draw", "away"]
    missing_keys = [k for k in required_keys if k not in odds]
    if missing_keys:
        raise ValueError("Keine Quoten für diesen Markt verfügbar")
    return odds


def dynamic_ttl(matches: list) -> int:
    now = time.time()
    soonest = None
    for m in matches:
        ct = m.get("raw_match", m).get("commence_time", "")
        if ct:
            try:
                dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
                diff = dt.timestamp() - now
                if diff > 0 and (soonest is None or diff < soonest):
                    soonest = diff
            except Exception:
                pass
    if soonest is None:
        return 3600
    if soonest > 86400:
        return 43200
    if soonest > 7200:
        return 3600
    return 900


def fetch_or_cache_totals(event_id: str, raw_match: dict, odds_engine, cache_collection, ttl: int = 3600, fetch_if_missing: bool = True) -> dict:
    cache_key = f"totals_{event_id}"
    entry = {}
    try:
        doc = cache_collection.find_one({"_id": cache_key})
        if doc:
            entry = doc
    except Exception:
        pass

    if entry and (time.time() - entry.get("timestamp", 0) < ttl):
        totals_bookmakers = entry.get("bookmakers", [])
    elif fetch_if_missing:
        try:
            event_data = odds_engine.get_event_odds(event_id, market="totals")
            totals_bookmakers = event_data.get("bookmakers", [])
            cache_collection.update_one(
                {"_id": cache_key},
                {"$set": {"timestamp": time.time(), "bookmakers": totals_bookmakers}},
                upsert=True
            )
        except Exception as e:
            print(f"Totals fetch failed for {event_id}: {e}")
            totals_bookmakers = []
    else:
        totals_bookmakers = []

    if not totals_bookmakers:
        return raw_match

    existing = {b["key"]: b for b in raw_match.get("bookmakers", [])}
    for tb in totals_bookmakers:
        key = tb.get("key")
        if key in existing:
            have_keys = {m["key"] for m in existing[key].get("markets", [])}
            for mkt in tb.get("markets", []):
                if mkt["key"] not in have_keys:
                    existing[key]["markets"].append(mkt)
        else:
            existing[key] = tb

    merged = dict(raw_match)
    merged["bookmakers"] = list(existing.values())
    return merged
