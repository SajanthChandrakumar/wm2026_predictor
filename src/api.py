import os
import sys
import json
import time
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.odds_engine import OddsApiEngine
from src.math_engine import MathEngine

app = FastAPI(title="WM 2026 Predictor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEAM_MAPPING = {
    "United States": "United States", "USA": "United States",
    "Korea Republic": "South Korea", "South Korea": "South Korea",
    "Czech Republic": "Czech Republic", "Czechia": "Czech Republic",
    "IR Iran": "Iran", "Côte d'Ivoire": "Ivory Coast", "Ivory Coast": "Ivory Coast",
    "Saudi Arabia": "Saudi Arabia", "KSA": "Saudi Arabia"
}

DISPLAY_MAPPING = {
    "United States": "🇺🇸 USA", "USA": "🇺🇸 USA",
    "South Korea": "🇰🇷 South Korea", "Korea Republic": "🇰🇷 South Korea",
    "Iran": "🇮🇷 Iran", "IR Iran": "🇮🇷 Iran",
    "Czech Republic": "🇨🇿 Czech Republic", "Czechia": "🇨🇿 Czech Republic",
    "Ivory Coast": "🇨🇮 Ivory Coast", "Côte d'Ivoire": "🇨🇮 Ivory Coast",
    "Argentina": "🇦🇷 Argentina", "France": "🇫🇷 France",
    "Germany": "🇩🇪 Germany", "Spain": "🇪🇸 Spain",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 England", "Brazil": "🇧🇷 Brazil",
    "Portugal": "🇵🇹 Portugal", "Netherlands": "🇳🇱 Netherlands",
    "Italy": "🇮🇹 Italy", "Belgium": "🇧🇪 Belgium",
}

elo_csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'elo_ratings.csv')
if not os.path.exists(elo_csv_path):
    os.makedirs(os.path.dirname(elo_csv_path), exist_ok=True)
    pd.DataFrame({
        "team_code": ["GER", "ARG", "FRA"],
        "team_name": ["Deutschland", "Argentinien", "Frankreich"],
        "elo_rating": [1980, 2140, 2090]
    }).to_csv(elo_csv_path, index=False)

math_engine = MathEngine(elo_csv_path, TEAM_MAPPING)

def extract_odds(match):
    home_team = match.get("home_team")
    away_team = match.get("away_team")
    odds = {}
    if "bookmakers" in match:
        for bookie in match["bookmakers"]:
            for market in bookie.get("markets", []):
                if market["key"] == "h2h":
                    for outcome in market.get("outcomes", []):
                        if outcome["name"] == home_team and "home" not in odds:
                            odds["home"] = outcome["price"]
                        elif outcome["name"] == away_team and "away" not in odds:
                            odds["away"] = outcome["price"]
                        elif outcome["name"] == "Draw" and "draw" not in odds:
                            odds["draw"] = outcome["price"]
                elif market["key"] == "totals":
                    for outcome in market.get("outcomes", []):
                        if outcome["name"] == "Over" and outcome.get("point", 2.5) == 2.5 and "over25" not in odds:
                            odds["over25"] = outcome["price"]
                        elif outcome["name"] == "Under" and outcome.get("point", 2.5) == 2.5 and "under25" not in odds:
                            odds["under25"] = outcome["price"]
            if all(k in odds for k in ["home", "draw", "away", "over25"]):
                break
    if all(k in odds for k in ["home", "draw", "away"]) and "over25" not in odds:
        odds["over25"] = 1.90
        odds["under25"] = 1.90
    required_keys = ["home", "draw", "away", "over25"]
    missing_keys = [k for k in required_keys if k not in odds]
    if missing_keys:
        raise ValueError("Keine Quoten für diesen Markt verfügbar")
    return odds

CACHE_TTL = 3600  # 1 Stunde in Sekunden
cache_file_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'matches_cache.json')

@app.get("/api/matches")
def get_matches(force: bool = False):
    """
    Holt die Spiele. Nutzt den Cache, es sei denn, force=True wird übergeben.
    """
    # 1. Cache prüfen (Wenn Daten da sind, nicht älter als 1 Stunde und kein Force-Refresh verlangt wird)
    if not force and os.path.exists(cache_file_path):
        try:
            with open(cache_file_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                timestamp = cached_data.get("timestamp", 0)
                data = cached_data.get("data")
                if data is not None and (time.time() - timestamp < CACHE_TTL):
                    return data
        except json.JSONDecodeError:
            pass
        
    # 2. API Call (Nur wenn der Cache leer/abgelaufen ist oder der User den Button drückt)
    engine = OddsApiEngine()
    try:
        data = engine.get_world_cup_odds(market="h2h,totals")
    except Exception:
        data = engine.get_world_cup_odds(market="h2h")
    
    results = []
    for m in data:
        home_raw = m.get("home_team")
        away_raw = m.get("away_team")
        try:
            odds = extract_odds(m)
            
            try:
                math_engine.merge_odds_and_elo([m])
                prob_home = 1.0 / odds["home"]
                prob_draw = 1.0 / odds["draw"]
                prob_away = 1.0 / odds["away"]
                prob_over25 = 1.0 / odds["over25"]
                
                xg_h, xg_a = math_engine.derive_xg_from_odds(
                    prob_home, prob_draw, prob_away, prob_over25
                )
                sm = math_engine.generate_exact_score_matrix(xg_h, xg_a, max_goals=5)
                df_xp = math_engine.calculate_expected_points(sm, is_ko_phase=False)
                
                if not df_xp.empty:
                    top_tip = df_xp.iloc[0]["Tipp"]
                    max_xp = float(df_xp.iloc[0]["xP"])
                else:
                    top_tip = "N/A"
                    max_xp = 0.0
            except Exception:
                top_tip = "N/A"
                max_xp = 0.0

            results.append({
                "id": m.get("id"),
                "home_team": home_raw,
                "away_team": away_raw,
                "home_disp": DISPLAY_MAPPING.get(home_raw, home_raw),
                "away_disp": DISPLAY_MAPPING.get(away_raw, away_raw),
                "odds": odds,
                "top_tip": top_tip,
                "max_xp": max_xp,
                "raw_match": m
            })
        except ValueError:
            continue
            
    # 3. Cache aktualisieren
    try:
        os.makedirs(os.path.dirname(cache_file_path), exist_ok=True)
        with open(cache_file_path, "w", encoding="utf-8") as f:
            json.dump({"timestamp": time.time(), "data": results}, f, indent=4)
    except Exception as e:
        print(f"Fehler beim Speichern des Caches: {e}")
    
    return results

@app.post("/api/predict")
def predict_match(payload: dict):
    match_data = payload.get("match")
    is_ko = payload.get("is_ko", False)
    
    if not match_data:
        raise HTTPException(status_code=400, detail="Match data required")
        
    try:
        math_engine.merge_odds_and_elo([match_data])
        odds = extract_odds(match_data)
        
        prob_home = 1.0 / odds["home"]
        prob_draw = 1.0 / odds["draw"]
        prob_away = 1.0 / odds["away"]
        prob_over25 = 1.0 / odds["over25"]
        
        xg_home, xg_away = math_engine.derive_xg_from_odds(
            prob_home=prob_home, prob_draw=prob_draw, prob_away=prob_away, prob_over25=prob_over25
        )
        
        if is_ko:
            xg_home *= 1.33
            xg_away *= 1.33
            
        score_matrix = math_engine.generate_exact_score_matrix(xg_home, xg_away, max_goals=5)
        xp_df = math_engine.calculate_expected_points(score_matrix, is_ko_phase=is_ko)
        
        matrix_dict = {}
        for row in score_matrix.index:
            matrix_dict[row] = {}
            for col in score_matrix.columns:
                matrix_dict[row][col] = score_matrix.loc[row, col]
                
        max_prob = score_matrix.values.max()
                
        return {
            "xg_home": xg_home,
            "xg_away": xg_away,
            "matrix": matrix_dict,
            "max_prob": max_prob,
            "xp_tips": xp_df.to_dict(orient="records")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/quota")
def get_quota():
    quota_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'api_quota.json')
    if os.path.exists(quota_path):
        with open(quota_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"remaining": "Unknown", "used": "Unknown"}

@app.post("/api/sync_elo")
def sync_elo():
    odds_engine = OddsApiEngine()
    processed_json_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed_matches.json')
    try:
        completed_matches = odds_engine.get_completed_scores(days_from=3)
        updates = math_engine.update_elo_from_api_scores(
            api_scores=completed_matches, 
            processed_matches_file=processed_json_path
        )
        if updates > 0:
            math_engine.elo_df.to_csv(math_engine.elo_csv_path, index=False)
            return {"status": "success", "updates": updates}
        else:
            return {"status": "info", "message": "No new matches."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
