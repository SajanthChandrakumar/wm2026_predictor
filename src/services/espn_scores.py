"""
ESPN scoreboard fetcher — public, no auth, no quota.
Returns completed WC fixtures normalized to the same shape the legacy
odds-engine `get_completed_scores` produced, so `perform_elo_sync` and
`math_engine.update_elo_from_api_scores` can consume it unchanged.
"""
import requests
from datetime import datetime, timedelta, timezone

ENDPOINT = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"

# ESPN uses a few names that differ from what /api/matches / TEAM_MAPPING settled on.
# Keep this tight — only the names that actually clash.
ESPN_NAME_FIXUP = {
    "Congo DR": "DR Congo",
    "Bosnia-Herzegovina": "Bosnia & Herzegovina",
    "Czechia": "Czech Republic",
}


def _canon(name: str) -> str:
    return ESPN_NAME_FIXUP.get(name, name)


def _fetch_range(start_date: str, end_date: str) -> list[dict]:
    resp = requests.get(ENDPOINT, params={"dates": f"{start_date}-{end_date}"}, timeout=10)
    resp.raise_for_status()
    return resp.json().get("events", []) or []


def get_completed_scores(days_from: int = 30) -> list[dict]:
    to_dt = datetime.now(timezone.utc).date()
    from_dt = to_dt - timedelta(days=days_from)
    events = _fetch_range(from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d"))

    out = []
    for e in events:
        comp = (e.get("competitions") or [{}])[0]
        status_type = (comp.get("status") or {}).get("type") or {}
        completed = bool(status_type.get("completed"))
        detail = status_type.get("detail", "")
        # FT, AET, PEN — anything else (HT, Live, etc) → not graded
        if not completed or detail not in ("FT", "AET", "PEN"):
            continue

        competitors = comp.get("competitors") or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue

        home_name = _canon((home.get("team") or {}).get("displayName", ""))
        away_name = _canon((away.get("team") or {}).get("displayName", ""))
        if not home_name or not away_name:
            continue

        round_name = ((e.get("season") or {}).get("slug") or "").replace("-", " ")

        out.append({
            "id": str(e.get("id", "")),
            "completed": True,
            "home_team": home_name,
            "away_team": away_name,
            "commence_time": e.get("date", ""),
            "round": round_name,
            "scores": [
                {"name": home_name, "score": str(home.get("score"))},
                {"name": away_name, "score": str(away.get("score"))},
            ],
        })
    return out
