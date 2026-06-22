import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

class OddsApiEngine:
    BASE_URL = "https://api.the-odds-api.com/v4/sports"
    SPORT = "soccer_fifa_world_cup"

    def __init__(self):
        self.api_key = os.getenv("ODDS_API_KEY")
        if not self.api_key or self.api_key == "your_key_here":
            raise ValueError("ODDS_API_KEY is missing or invalid in the environment variables. Please set it in the .env file.")

    def _update_quota(self, headers: dict):
        remaining = headers.get("x-requests-remaining", "Unknown")
        used = headers.get("x-requests-used", "Unknown")
        
        quota_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'api_quota_odds.json')
        os.makedirs(os.path.dirname(quota_path), exist_ok=True)
        
        with open(quota_path, 'w', encoding='utf-8') as f:
            json.dump({"remaining": remaining, "used": used}, f, indent=4)

    def get_world_cup_odds(self, market: str = "h2h") -> list[dict]:
        """Fetch odds for all upcoming WC matches. Each market string costs 1 API request."""
        url = f"{self.BASE_URL}/{self.SPORT}/odds"
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

    def get_event_odds(self, event_id: str, market: str = "totals") -> dict:
        """Fetch odds for a single event — costs 1 request regardless of markets count."""
        url = f"{self.BASE_URL}/{self.SPORT}/events/{event_id}/odds"
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
        response = requests.get(url, params=params)
        response.raise_for_status()
        self._update_quota(response.headers)
        return response.json()
