import os
import sys
import json
import time
import statistics
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler

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
    "Saudi Arabia": "Saudi Arabia", "KSA": "Saudi Arabia",
    "Turkey": "Türkiye", "Türkiye": "Türkiye",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina"
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
    """
    Konsens-Quoten: Median über alle Buchmacher statt erstbester Quote.
    Der Markt-Median ist robuster gegen Ausreisser einzelner Anbieter.
    """
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
                true_probs = MathEngine.remove_margin(odds["home"], odds["draw"], odds["away"])
                prob_home = true_probs["home"]
                prob_draw = true_probs["draw"]
                prob_away = true_probs["away"]
                if "over25" in odds and "under25" in odds:
                    raw_over = 1.0 / odds["over25"]
                    raw_under = 1.0 / odds["under25"]
                    prob_over25 = raw_over / (raw_over + raw_under)
                else:
                    prob_over25 = None

                xg_h, xg_a = math_engine.derive_xg_from_odds(
                    prob_home, prob_draw, prob_away, prob_over25
                )
                sm = math_engine.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
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
    home_resting = payload.get("home_resting", False)
    away_resting = payload.get("away_resting", False)
    aggressiveness = float(payload.get("aggressiveness", 0.0))

    if not match_data:
        raise HTTPException(status_code=400, detail="Match data required")
        
    try:
        math_engine.merge_odds_and_elo([match_data])
        odds = extract_odds(match_data)
        
        true_probs = MathEngine.remove_margin(odds["home"], odds["draw"], odds["away"])
        b_prob_home = true_probs["home"]
        b_prob_draw = true_probs["draw"]
        b_prob_away = true_probs["away"]
        if "over25" in odds and "under25" in odds:
            raw_over = 1.0 / odds["over25"]
            raw_under = 1.0 / odds["under25"]
            prob_over25 = raw_over / (raw_over + raw_under)
        else:
            prob_over25 = None

        elo_prob_home, elo_prob_away = math_engine.get_match_elo_probabilities(
            match_data.get("home_team"),
            match_data.get("away_team"),
            home_resting,
            away_resting
        )

        # Blend only within the win/loss pool so draw probability stays fixed
        win_loss_pool = b_prob_home + b_prob_away
        blend_home = (b_prob_home / win_loss_pool * 0.7 + elo_prob_home * 0.3) * win_loss_pool
        blend_away = (b_prob_away / win_loss_pool * 0.7 + elo_prob_away * 0.3) * win_loss_pool
        prob_home = blend_home
        prob_away = blend_away
        prob_draw = b_prob_draw

        xg_home, xg_away = math_engine.derive_xg_from_odds(
            prob_home=prob_home, prob_draw=prob_draw, prob_away=prob_away, prob_over25=prob_over25
        )

        if is_ko:
            # ET only happens when the match is still drawn after 90 min.
            # Weight the extra ~30 min of goals by that probability.
            base_matrix = math_engine.generate_exact_score_matrix(xg_home, xg_away, max_goals=10)
            p_draw_90 = float(np.sum(np.diag(base_matrix.values)))
            et_factor = 1 + p_draw_90 / 3
            xg_home *= et_factor
            xg_away *= et_factor

        score_matrix = math_engine.generate_exact_score_matrix(xg_home, xg_away, max_goals=10)
        xp_df = math_engine.calculate_expected_points(score_matrix, is_ko_phase=is_ko)
        pool_df = math_engine.calculate_pool_optimal_tips(score_matrix, is_ko_phase=is_ko, aggressiveness=aggressiveness)

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
            "xp_tips": xp_df.to_dict(orient="records"),
            "pool_tips": pool_df.to_dict(orient="records")
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

@app.get("/api/elo_history")
def get_elo_history():
    history_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'elo_history.json')
    if os.path.exists(history_path):
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def perform_elo_sync() -> dict:
    print("Automated Elo sync triggered...")
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
            print(f"Automated Elo sync completed: {updates} updates.")
            return {"status": "success", "updates": updates}
        else:
            print("Automated Elo sync completed: No new matches.")
            return {"status": "info", "message": "No new matches."}
    except Exception as e:
        print(f"Automated Elo sync failed: {str(e)}")
        raise e

@app.post("/api/sync_elo")
def sync_elo():
    try:
        return perform_elo_sync()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
def startup_event():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(perform_elo_sync, 'cron', hour=4, minute=0)
    scheduler.start()
    print("Scheduler started. Elo sync scheduled for 04:00 AM daily.")

frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
