import os
import json
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()


class OddsApiEngine:
    """
    API-Football (api-sports.io) v3 client for FIFA World Cup data.

    World Cup league ID = 1 in API-Football. If the WM 2026 season uses a
    different identifier, override WC_LEAGUE_ID before constructing the engine.
    """
    BASE_URL = "https://v3.football.api-sports.io"
    WC_LEAGUE_ID = 1
    SEASON = 2026

    def __init__(self):
        self.api_key = os.getenv("API_FOOTBALL_KEY") or os.getenv("ODDS_API_KEY")
        if not self.api_key or self.api_key == "your_key_here":
            raise ValueError(
                "API_FOOTBALL_KEY is missing or invalid. Set it in your .env file "
                "(see https://dashboard.api-football.com/profile?access)."
            )
        self._headers = {"x-apisports-key": self.api_key}

    def _request(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.BASE_URL}{path}"
        response = requests.get(url, headers=self._headers, params=params or {})
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

    def get_world_cup_odds(self, market: str = "h2h") -> list[dict]:
        """
        Returns WC odds enriched with team names. API-Football's /odds endpoint
        omits team names (only fixture_id), so this method also calls /fixtures
        and merges. The `market` argument is preserved for backwards compatibility
        but ignored — API-Football returns ALL bookmaker markets (Match Winner +
        Over/Under 2.5) in a single response, so no separate totals call is needed.
        """
        fixtures_resp = self._request("/fixtures", {
            "league": self.WC_LEAGUE_ID,
            "season": self.SEASON,
        })
        fixtures_by_id = {
            f["fixture"]["id"]: f for f in fixtures_resp.get("response", [])
        }

        odds_resp = self._request("/odds", {
            "league": self.WC_LEAGUE_ID,
            "season": self.SEASON,
        })
        merged = []
        for odd in odds_resp.get("response", []):
            fid = odd.get("fixture", {}).get("id")
            fixture = fixtures_by_id.get(fid)
            if not fixture:
                continue
            merged.append({
                "league": odd.get("league") or fixture.get("league"),
                "fixture": fixture["fixture"],
                "teams": fixture["teams"],
                "bookmakers": odd.get("bookmakers", []),
            })
        return merged

    def get_completed_scores(self, days_from: int = 3) -> list[dict]:
        """
        Returns finished WC fixtures (status FT) within the last `days_from` days.
        Bounded by from/to query params to keep the payload small.
        """
        to_dt = datetime.now(timezone.utc).date()
        from_dt = to_dt - timedelta(days=days_from)
        resp = self._request("/fixtures", {
            "league": self.WC_LEAGUE_ID,
            "season": self.SEASON,
            "status": "FT",
            "from": from_dt.isoformat(),
            "to": to_dt.isoformat(),
        })
        return resp.get("response", [])
