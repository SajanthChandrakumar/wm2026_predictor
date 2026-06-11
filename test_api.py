import os
from dotenv import load_dotenv
import requests

load_dotenv()
API_KEY = os.environ.get("ODDS_API_KEY")

url = f"https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds/?apiKey={API_KEY}&regions=eu&markets=h2h,totals"
response = requests.get(url)
data = response.json()

if isinstance(data, list) and len(data) > 0:
    print(f"Got {len(data)} matches.")
    match = data[0]
    print(f"Match: {match.get('home_team')} vs {match.get('away_team')}")
    for b in match.get('bookmakers', []):
        markets = [m['key'] for m in b.get('markets', [])]
        print(f"Bookie: {b['key']}, Markets: {markets}")
else:
    print("No data or error:", data)
