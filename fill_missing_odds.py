import json
import csv

def load_elo_lookup(csv_path="data/elo_ratings.csv"):
    """Load Elo ratings from CSV into a dict: team_name -> rating."""
    lookup = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lookup[row["team_name"]] = float(row["elo_rating"])
    return lookup

def elo_to_decimal_odds(elo_home: float, elo_away: float) -> dict:
    """Convert Elo ratings to realistic decimal bookmaker odds."""
    # Win probabilities from Elo
    diff = elo_home - elo_away
    p_home_raw = 1 / (1 + 10 ** (-diff / 400))
    p_away_raw = 1 - p_home_raw
    
    # Draw probability scaled by closeness (closer Elo -> higher draw chance)
    draw_base = 0.22
    closeness = 1 - abs(diff) / 800  # 1.0 when equal, 0.0 at 800+ diff
    p_draw = draw_base * max(closeness, 0.3)
    
    # Scale home/away to fit
    scale = 1 - p_draw
    p_home = p_home_raw * scale
    p_away = p_away_raw * scale
    
    # Convert to decimal odds with ~5% bookmaker margin
    margin = 1.05
    odds_home = round(margin / p_home, 2)
    odds_draw = round(margin / p_draw, 2)
    odds_away = round(margin / p_away, 2)
    
    return {"home": odds_home, "draw": odds_draw, "away": odds_away}

def fill_missing_odds(archive_path="data/live_archive.json", out_path="data/live_archive_filled.json"):
    with open(archive_path, "r", encoding="utf-8") as f:
        archive = json.load(f)
    
    elo_lookup = load_elo_lookup()
    filled = 0
    
    for match_id, match in archive.items():
        snap = match.get("pre_match_snapshot") or {}
        odds = snap.get("odds")
        
        if not odds or not all(k in odds for k in ("home", "draw", "away")):
            meta = match.get("metadata", {})
            home_team = meta.get("home_team", "")
            away_team = meta.get("away_team", "")
            
            # Look up Elo from CSV
            elo_home = elo_lookup.get(home_team, 1500.0)
            elo_away = elo_lookup.get(away_team, 1500.0)
            
            # Generate realistic odds
            odds = elo_to_decimal_odds(elo_home, elo_away)
            
            # Also fill in elo_state if missing
            if not snap.get("elo_state") or snap["elo_state"].get("home_rating") is None:
                snap["elo_state"] = {"home_rating": elo_home, "away_rating": elo_away}
            
            snap["odds"] = odds
            match["pre_match_snapshot"] = snap
            filled += 1
            print(f"  Filled: {home_team:20s} vs {away_team:20s} | Elo: {elo_home:.0f}/{elo_away:.0f} | Odds: H={odds['home']}, D={odds['draw']}, A={odds['away']}")
    
    print(f"\nFilled odds for {filled} matches.")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2)
    print(f"Saved filled archive to {out_path}")

if __name__ == "__main__":
    fill_missing_odds()
