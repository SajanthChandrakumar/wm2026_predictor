import os
import sys
import json
import time
import statistics
from datetime import datetime, timezone
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

cache_file_path    = os.path.join(os.path.dirname(__file__), '..', 'data', 'matches_cache.json')
totals_cache_path  = os.path.join(os.path.dirname(__file__), '..', 'data', 'totals_cache.json')
scores_cache_path  = os.path.join(os.path.dirname(__file__), '..', 'data', 'scores_cache.json')
archive_json_path  = os.path.join(os.path.dirname(__file__), '..', 'data', 'prediction_archive.json')

TOTALS_CACHE_TTL = 3600   # 1h per match
SCORES_CACHE_TTL = 1800   # 30 min — avoids burning quota on repeated manual syncs


def _dynamic_ttl(matches: list) -> int:
    """Return cache TTL in seconds based on soonest upcoming kickoff."""
    now = time.time()
    soonest = None
    for m in matches:
        ct = m.get("raw_match", m).get("commence_time", "")
        if ct:
            try:
                dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
                diff = dt.timestamp() - now
                if diff > 0 and (soonest is None or diff < soonest):
                    soonest = diff
            except Exception:
                pass
    if soonest is None:
        return 3600
    if soonest > 86400:   # > 24h away
        return 43200      # 12h
    if soonest > 7200:    # 2h – 24h
        return 3600       # 1h
    return 900            # < 2h → 15 min


def _fetch_or_cache_totals(event_id: str, raw_match: dict) -> dict:
    """
    Return raw_match augmented with totals bookmakers, fetching from the
    single-event endpoint (1 request) only if the per-match cache is stale.
    """
    totals_cache = {}
    if os.path.exists(totals_cache_path):
        try:
            with open(totals_cache_path, 'r', encoding='utf-8') as f:
                totals_cache = json.load(f)
        except Exception:
            pass

    entry = totals_cache.get(event_id, {})
    if entry and (time.time() - entry.get("timestamp", 0) < TOTALS_CACHE_TTL):
        totals_bookmakers = entry.get("bookmakers", [])
    else:
        try:
            engine = OddsApiEngine()
            event_data = engine.get_event_odds(event_id, market="totals")
            totals_bookmakers = event_data.get("bookmakers", [])
            totals_cache[event_id] = {"timestamp": time.time(), "bookmakers": totals_bookmakers}
            os.makedirs(os.path.dirname(totals_cache_path), exist_ok=True)
            with open(totals_cache_path, 'w', encoding='utf-8') as f:
                json.dump(totals_cache, f, indent=4)
        except Exception as e:
            print(f"Totals fetch failed for {event_id}: {e}")
            totals_bookmakers = []

    if not totals_bookmakers:
        return raw_match

    # Merge totals markets into existing bookmaker entries
    existing = {b["key"]: b for b in raw_match.get("bookmakers", [])}
    for tb in totals_bookmakers:
        key = tb.get("key")
        if key in existing:
            have_keys = {m["key"] for m in existing[key].get("markets", [])}
            for mkt in tb.get("markets", []):
                if mkt["key"] not in have_keys:
                    existing[key]["markets"].append(mkt)
        else:
            existing[key] = tb

    merged = dict(raw_match)
    merged["bookmakers"] = list(existing.values())
    return merged

@app.get("/api/matches")
def get_matches(force: bool = False):
    """
    Holt die Spiele. Nutzt den Cache, es sei denn, force=True wird übergeben.
    """
    math_engine.reload_elo_data()
    # 1. Cache prüfen — TTL is dynamic based on soonest kickoff time
    if not force and os.path.exists(cache_file_path):
        try:
            with open(cache_file_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                timestamp = cached_data.get("timestamp", 0)
                data = cached_data.get("data")
                if data is not None:
                    ttl = _dynamic_ttl(data)
                    if time.time() - timestamp < ttl:
                        return data
        except json.JSONDecodeError:
            pass
        
    # 2. API Call — h2h only (1 request). Totals are fetched lazily per match on /api/predict.
    engine = OddsApiEngine()
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
            
    # 3. Cache aktualisieren — merge with existing so completed matches aren't lost
    try:
        os.makedirs(os.path.dirname(cache_file_path), exist_ok=True)
        existing_matches = {}
        if os.path.exists(cache_file_path):
            try:
                with open(cache_file_path, "r", encoding="utf-8") as f:
                    existing_matches = {m["id"]: m for m in json.load(f).get("data", [])}
            except Exception:
                pass
        for r in results:
            prev = existing_matches.get(r["id"])
            if prev:
                old_o, new_o = prev.get("odds", {}), r.get("odds", {})
                odds_changed = any(
                    abs(new_o.get(k, 0) - old_o.get(k, 0)) > 0.02
                    for k in ["home", "draw", "away"]
                )
                if not odds_changed:
                    continue  # keep old entry unchanged
            existing_matches[r["id"]] = r
        merged = sorted(existing_matches.values(), key=lambda m: m.get("raw_match", {}).get("commence_time", ""))
        with open(cache_file_path, "w", encoding="utf-8") as f:
            json.dump({"timestamp": time.time(), "data": merged}, f, indent=4)
    except Exception as e:
        print(f"Fehler beim Speichern des Caches: {e}")

    # 4. Archive: log new pre-match snapshots (only first time a match_id is seen)
    try:
        archive = {}
        if os.path.exists(archive_json_path):
            with open(archive_json_path, 'r', encoding='utf-8') as f:
                archive = json.load(f)

        changed = False
        for r in results:
            if r["id"] in archive or r["top_tip"] == "N/A":
                continue

            home_norm = TEAM_MAPPING.get(r["home_team"], r["home_team"])
            away_norm = TEAM_MAPPING.get(r["away_team"], r["away_team"])
            elo_rows_home = math_engine.elo_df.loc[math_engine.elo_df['team_name'] == home_norm, 'elo_rating']
            elo_rows_away = math_engine.elo_df.loc[math_engine.elo_df['team_name'] == away_norm, 'elo_rating']
            elo_home_val = float(elo_rows_home.values[0]) if not elo_rows_home.empty else 1500.0
            elo_away_val = float(elo_rows_away.values[0]) if not elo_rows_away.empty else 1500.0

            archive[r["id"]] = {
                "metadata": {
                    "home_team": r["home_team"],
                    "away_team": r["away_team"],
                    "home_disp": r["home_disp"],
                    "away_disp": r["away_disp"],
                    "is_ko_phase": False
                },
                "pre_match_snapshot": {
                    "timestamp_recorded": datetime.now(timezone.utc).isoformat(),
                    "odds": r["odds"],
                    "elo_state": {
                        "home_rating": elo_home_val,
                        "away_rating": elo_away_val
                    }
                },
                "prediction": {
                    "top_tip": r["top_tip"],
                    "max_xp": float(r["max_xp"])
                },
                "post_match_result": {
                    "status": "pending",
                    "actual_score": None,
                    "points_earned": None
                }
            }
            changed = True

        if changed:
            os.makedirs(os.path.dirname(archive_json_path), exist_ok=True)
            with open(archive_json_path, 'w', encoding='utf-8') as f:
                json.dump(archive, f, indent=4)
    except Exception as e:
        print(f"Archive logging failed: {e}")

    return results

@app.post("/api/predict")
def predict_match(payload: dict):
    math_engine.reload_elo_data()
    match_data = payload.get("match")
    is_ko = payload.get("is_ko", False)
    home_resting = payload.get("home_resting", False)
    away_resting = payload.get("away_resting", False)
    aggressiveness = float(payload.get("aggressiveness", 0.0))

    if not match_data:
        raise HTTPException(status_code=400, detail="Match data required")

    try:
        event_id = match_data.get("id", "")
        match_data = _fetch_or_cache_totals(event_id, match_data)

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

@app.get("/api/archive")
def get_archive():
    if os.path.exists(archive_json_path):
        try:
            with open(archive_json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

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
        # Scores cache: avoid burning quota when sync is triggered multiple times within 30 min
        scores_cache = {}
        if os.path.exists(scores_cache_path):
            try:
                with open(scores_cache_path, 'r', encoding='utf-8') as f:
                    scores_cache = json.load(f)
            except Exception:
                pass

        if time.time() - scores_cache.get("timestamp", 0) < SCORES_CACHE_TTL:
            completed_matches = scores_cache.get("data", [])
            print("Elo sync: using cached scores (< 30 min old)")
        else:
            completed_matches = odds_engine.get_completed_scores(days_from=3)
            try:
                os.makedirs(os.path.dirname(scores_cache_path), exist_ok=True)
                with open(scores_cache_path, 'w', encoding='utf-8') as f:
                    json.dump({"timestamp": time.time(), "data": completed_matches}, f, indent=4)
            except Exception as e:
                print(f"Scores cache write failed: {e}")

        updates = math_engine.update_elo_from_api_scores(
            api_scores=completed_matches,
            processed_matches_file=processed_json_path
        )
        if updates > 0:
            math_engine.elo_df.to_csv(math_engine.elo_csv_path, index=False)
            print(f"Automated Elo sync completed: {updates} updates.")

        # Post-match grading: score archived predictions against actual results
        try:
            archive = {}
            if os.path.exists(archive_json_path):
                with open(archive_json_path, 'r', encoding='utf-8') as f:
                    archive = json.load(f)

            graded = 0
            for match in completed_matches:
                match_id = match.get("id")
                if not match_id or not match.get("completed"):
                    continue
                if match_id not in archive or archive[match_id]["post_match_result"]["status"] != "pending":
                    continue

                home_team = match.get("home_team")
                away_team = match.get("away_team")
                scores = match.get("scores") or []
                home_score = next((s["score"] for s in scores if s["name"] == home_team), None)
                away_score = next((s["score"] for s in scores if s["name"] == away_team), None)
                if home_score is None or away_score is None:
                    continue
                try:
                    home_score = int(home_score)
                    away_score = int(away_score)
                except ValueError:
                    continue

                actual_score_str = f"{home_score}:{away_score}"
                tipped = archive[match_id]["prediction"]["top_tip"]
                is_ko = archive[match_id]["metadata"]["is_ko_phase"]

                archive[match_id]["post_match_result"]["status"] = "completed"
                archive[match_id]["post_match_result"]["actual_score"] = actual_score_str
                archive[match_id]["post_match_result"]["points_earned"] = MathEngine.calculate_actual_points(
                    tipped, actual_score_str, is_ko
                )
                graded += 1

            if graded > 0:
                with open(archive_json_path, 'w', encoding='utf-8') as f:
                    json.dump(archive, f, indent=4)
                print(f"Archive grading completed: {graded} predictions scored.")
        except Exception as e:
            print(f"Archive grading failed: {e}")

        if updates > 0:
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
