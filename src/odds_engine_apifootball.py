"""
Drop-in replacement for src.odds_engine.OddsApiEngine that hits API-Football
(api-sports.io) instead of The Odds API. Returns data normalized to the legacy
Odds-API shape so the rest of the codebase needs zero changes.

Activate via the `USE_API_FOOTBALL=true` env flag — see src/api.py for the switch.

World Cup league ID = 1 on API-Football. If that ID ever changes for a
different season schema, override WC_LEAGUE_ID before constructing the engine.
"""
import os
import json
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()


class OddsApiEngine:
    BASE_URL = "https://v3.football.api-sports.io"
    WC_LEAGUE_ID = 1
    SEASON = 2026

    def __init__(self):
        self.api_key = os.getenv("API_FOOTBALL_KEY")
        if not self.api_key or self.api_key == "your_key_here":
            raise ValueError(
                "API_FOOTBALL_KEY missing or invalid in .env. "
                "Get one at https://dashboard.api-football.com/profile?access"
            )
        self._headers = {"x-apisports-key": self.api_key}

    def _request(self, path: str, params: dict | None = None) -> dict:
        response = requests.get(f"{self.BASE_URL}{path}", headers=self._headers, params=params or {})
        response.raise_for_status()
        self._update_quota(response.headers)
        return response.json()

    def _update_quota(self, headers) -> None:
        remaining = headers.get("x-ratelimit-requests-remaining", "Unknown")
        limit = headers.get("x-ratelimit-requests-limit", "Unknown")
        try:
            used = int(limit) - int(remaining)
        except (ValueError, TypeError):
            used = "Unknown"
        quota_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'api_quota.json')
        os.makedirs(os.path.dirname(quota_path), exist_ok=True)
        with open(quota_path, 'w', encoding='utf-8') as f:
            json.dump({"remaining": remaining, "used": used, "limit": limit}, f, indent=4)

    # ── Public API (matches src.odds_engine.OddsApiEngine signatures) ────────

    def get_world_cup_odds(self, market: str = "h2h") -> list[dict]:
        """
        Two requests: /fixtures (for team names + kickoff time) and /odds (for
        bookmaker quotes). Merged + normalized into the legacy Odds-API shape:

            {
              id, sport_key, commence_time,
              home_team, away_team,
              bookmakers: [{key, title, markets: [{key, outcomes: [{name, price, point?}]}]}]
            }
        """
        fixtures_resp = self._request("/fixtures", {
            "league": self.WC_LEAGUE_ID,
            "season": self.SEASON,
        })
        fixtures_by_id = {f["fixture"]["id"]: f for f in fixtures_resp.get("response", [])}

        odds_resp = self._request("/odds", {
            "league": self.WC_LEAGUE_ID,
            "season": self.SEASON,
        })

        out = []
        for odd in odds_resp.get("response", []):
            fid = (odd.get("fixture") or {}).get("id")
            fixture = fixtures_by_id.get(fid)
            if not fixture:
                continue
            normalized = self._normalize_odds_entry(fixture, odd)
            if normalized:
                out.append(normalized)
        return out

    def get_event_odds(self, event_id: str, market: str = "totals") -> dict:
        """
        Compatibility shim — API-Football already returns Match Winner + Goals
        Over/Under in the same /odds payload, so a separate per-event call is
        unnecessary. Returning the cached entry from /odds keeps the legacy
        _fetch_or_cache_totals code path happy if any caller still uses it.
        """
        resp = self._request("/odds", {
            "league": self.WC_LEAGUE_ID,
            "season": self.SEASON,
            "fixture": event_id,
        })
        entries = resp.get("response", [])
        if not entries:
            return {"bookmakers": []}
        odd = entries[0]
        fid = (odd.get("fixture") or {}).get("id")

        # Need the fixture for team names — minimal call
        fix_resp = self._request("/fixtures", {"id": fid})
        fixtures = fix_resp.get("response", [])
        if not fixtures:
            return {"bookmakers": []}
        normalized = self._normalize_odds_entry(fixtures[0], odd)
        return normalized or {"bookmakers": []}

    def get_completed_scores(self, days_from: int = 3) -> list[dict]:
        """
        Finished WC fixtures within the last `days_from` days, normalized into
        the legacy Odds-API scores shape: {id, completed, home_team, away_team,
        commence_time, scores: [{name, score}]}.
        """
        to_dt = datetime.now(timezone.utc).date()
        from_dt = to_dt - timedelta(days=days_from)
        resp = self._request("/fixtures", {
            "league": self.WC_LEAGUE_ID,
            "season": self.SEASON,
            "from": from_dt.isoformat(),
            "to": to_dt.isoformat(),
        })
        out = []
        for m in resp.get("response", []):
            fixture = m.get("fixture") or {}
            teams = m.get("teams") or {}
            goals = m.get("goals") or {}
            status = (fixture.get("status") or {}).get("short")
            completed = status in ("FT", "AET", "PEN")
            home = (teams.get("home") or {}).get("name")
            away = (teams.get("away") or {}).get("name")
            if not home or not away:
                continue
            out.append({
                "id": str(fixture.get("id", "")),
                "completed": completed,
                "home_team": home,
                "away_team": away,
                "commence_time": fixture.get("date", ""),
                "scores": (
                    [
                        {"name": home, "score": str(goals.get("home"))},
                        {"name": away, "score": str(goals.get("away"))},
                    ]
                    if completed and goals.get("home") is not None and goals.get("away") is not None
                    else None
                ),
            })
        return out

    # ── Internal normalizers ─────────────────────────────────────────────────

    @staticmethod
    def _normalize_odds_entry(fixture: dict, odd: dict) -> dict | None:
        teams = fixture.get("teams") or {}
        home = (teams.get("home") or {}).get("name")
        away = (teams.get("away") or {}).get("name")
        fixture_meta = fixture.get("fixture") or {}
        if not home or not away or not fixture_meta.get("id"):
            return None

        legacy_bookies = []
        for b in odd.get("bookmakers", []):
            markets = []
            h2h_outcomes = []
            totals_outcomes = []
            for bet in b.get("bets", []):
                bid = bet.get("id")
                if bid == 1:  # Match Winner
                    for v in bet.get("values", []):
                        try:
                            price = float(v["odd"])
                        except (KeyError, TypeError, ValueError):
                            continue
                        nm = v.get("value")
                        if nm == "Home":
                            h2h_outcomes.append({"name": home, "price": price})
                        elif nm == "Draw":
                            h2h_outcomes.append({"name": "Draw", "price": price})
                        elif nm == "Away":
                            h2h_outcomes.append({"name": away, "price": price})
                elif bid == 5:  # Goals Over/Under
                    for v in bet.get("values", []):
                        try:
                            price = float(v["odd"])
                        except (KeyError, TypeError, ValueError):
                            continue
                        nm = v.get("value", "")
                        if nm == "Over 2.5":
                            totals_outcomes.append({"name": "Over", "price": price, "point": 2.5})
                        elif nm == "Under 2.5":
                            totals_outcomes.append({"name": "Under", "price": price, "point": 2.5})
            if h2h_outcomes:
                markets.append({"key": "h2h", "outcomes": h2h_outcomes})
            if totals_outcomes:
                markets.append({"key": "totals", "outcomes": totals_outcomes})
            if markets:
                legacy_bookies.append({
                    "key": str(b.get("id", "")) or b.get("name", "unknown"),
                    "title": b.get("name", ""),
                    "markets": markets,
                })

        return {
            "id": str(fixture_meta["id"]),
            "sport_key": "soccer_fifa_world_cup",
            "commence_time": fixture_meta.get("date", ""),
            "home_team": home,
            "away_team": away,
            "bookmakers": legacy_bookies,
        }
