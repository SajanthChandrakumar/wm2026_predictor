import os
import requests
from dotenv import load_dotenv

from src.competitions import get_competition

try:
    from src.quota_store import write_quota
except ImportError:
    from quota_store import write_quota

load_dotenv()

class OddsApiEngine:
    BASE_URL = os.getenv("ODDS_API_BASE_URL", "https://api.the-odds-api.com/v4/sports")
    SPORT = "soccer_fifa_world_cup"

    def __init__(self):
        self.api_key = os.getenv("ODDS_API_KEY")
        if not self.api_key or self.api_key == "your_key_here":
            raise ValueError("ODDS_API_KEY is missing or invalid in the environment variables. Please set it in the .env file.")

    def _update_quota(self, headers: dict):
        remaining = headers.get("x-requests-remaining", "Unknown")
        used = headers.get("x-requests-used", "Unknown")
        write_quota("odds", {"remaining": remaining, "used": used})

    def sport_for(self, competition=None) -> str:
        comp = get_competition(competition)
        return os.getenv(f"ODDS_API_{comp.id.upper()}_SPORT_KEY", comp.odds_api_sport_key)

    def get_competition_odds(self, competition=None, market: str = "h2h,totals") -> list[dict]:
        """Fetch one bounded bulk quote set for a competition."""
        sport = self.sport_for(competition)
        url = f"{self.BASE_URL}/{sport}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": "eu",
            "markets": market,
            "oddsFormat": "decimal"
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        self._update_quota(response.headers)
        return response.json()

    get_odds = get_competition_odds

    def get_world_cup_odds(self, market: str = "h2h") -> list[dict]:
        """Compatibility wrapper retaining the legacy WC default."""
        return self.get_competition_odds("wc2026", market=market)

    def get_event_odds(self, event_id: str, market: str = "totals", competition=None) -> dict:
        """Fetch odds for a single event — costs 1 request regardless of markets count."""
        url = f"{self.BASE_URL}/{self.sport_for(competition)}/events/{event_id}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": "eu",
            "markets": market,
            "oddsFormat": "decimal"
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        self._update_quota(response.headers)
        return response.json()

    def get_completed_scores(self, days_from: int = 3) -> list[dict]:
        """Fetch scores for completed WC matches."""
        url = f"{self.BASE_URL}/{self.SPORT}/scores"
        params = {
            "apiKey": self.api_key,
            "daysFrom": days_from
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        self._update_quota(response.headers)
        return response.json()
