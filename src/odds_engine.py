import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class OddsApiEngine:
    """
    A client for the Odds API.
    """
    BASE_URL = "https://api.the-odds-api.com/v4/sports"

    def __init__(self):
        self.api_key = os.getenv("ODDS_API_KEY")
        if not self.api_key or self.api_key == "your_key_here":
            raise ValueError("ODDS_API_KEY is missing or invalid in the environment variables. Please set it in the .env file.")

    def _update_quota(self, headers: dict):
        import json
        import os
        remaining = headers.get("x-requests-remaining", "Unknown")
        used = headers.get("x-requests-used", "Unknown")
        
        quota_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'api_quota.json')
        os.makedirs(os.path.dirname(quota_path), exist_ok=True)
        
        with open(quota_path, 'w', encoding='utf-8') as f:
            json.dump({"remaining": remaining, "used": used}, f, indent=4)

    def get_world_cup_odds(self, market: str = "h2h") -> list[dict]:
        """
        Fetches odds for the FIFA World Cup.
        
        Args:
            market (str): The betting market to fetch (e.g., 'h2h', 'spreads', 'totals').
            
        Returns:
            list[dict]: A list of JSON objects containing the odds data.
        """
        sport_key = "soccer_fifa_world_cup"
        url = f"{self.BASE_URL}/{sport_key}/odds"
        
        params = {
            "apiKey": self.api_key,
            "regions": "eu",
            "markets": market,
            "oddsFormat": "decimal"
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        self._update_quota(response.headers)
        
        return response.json()

    def get_completed_scores(self, days_from: int = 5) -> list[dict]:
        """
        Fetches scores for completed FIFA World Cup matches.
        """
        sport_key = "soccer_fifa_world_cup"
        url = f"{self.BASE_URL}/{sport_key}/scores"
        
        params = {
            "apiKey": self.api_key,
            "daysFrom": days_from
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        self._update_quota(response.headers)
        
        return response.json()
