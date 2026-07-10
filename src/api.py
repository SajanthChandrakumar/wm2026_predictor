import os
import sys
import time
import json
import logging

import pandas as pd
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pymongo import MongoClient
import certifi
from slowapi import Limiter
from slowapi.util import get_remote_address

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

if os.getenv("USE_API_FOOTBALL", "").lower() in ("1", "true", "yes"):
    from src.odds_engine_apifootball import OddsApiEngine
    print("Odds engine: API-Football (api-sports.io)")
else:
    from src.odds_engine import OddsApiEngine
    print("Odds engine: The Odds API")

from src.math_engine import MathEngine
from src.quota_store import read_quota
from src.constants import TEAM_MAPPING, SCORES_CACHE_TTL, _is_ko_round
from src.services.archive import load_archive_from_db, upsert_archive_entry
from src.services.elo_sync import perform_elo_sync
from src.routes.matches import init_router as matches_router
from src.routes.predict import init_router as predict_router
from src.routes.custom_bot import init_router as custom_bot_router
from src.routes.simulate import init_router as simulate_router

app = FastAPI(title="WM 2026 Predictor API")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── MongoDB ──────────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable is required. Set it in your .env file.")
_mongo_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
_db = _mongo_client["wm2026_db"]
archive_collection = _db["archive"]
cache_collection = _db["cache"]
custom_bot_collection = _db["custom_bot"]

# ── CORS ─────────────────────────────────────────────────────
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Compress JSON payloads and static assets (the matches/archive responses
# are several hundred KB uncompressed).
app.add_middleware(GZipMiddleware, minimum_size=1024)

def _real_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)

limiter = Limiter(key_func=_real_ip)
app.state.limiter = limiter

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com; style-src 'self' 'unsafe-inline' fonts.googleapis.com; font-src 'self' fonts.gstatic.com; img-src 'self' data:"
    path = request.url.path
    if path.startswith("/assets/"):
        # Vite emits content-hashed filenames under /assets/ — safe to cache
        # forever; a new build changes the hash and busts the cache.
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path == "/" or path.endswith((".js", ".css", ".html")):
        # Everything unhashed (index.html, legacy frontend) must revalidate
        # every load (ETag → 304), or code changes silently fail to arrive.
        response.headers["Cache-Control"] = "no-cache"
    return response

# ── Engine init ──────────────────────────────────────────────
_data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(_data_dir, exist_ok=True)
elo_csv_path = os.path.join(_data_dir, 'elo_ratings.csv')
if not os.path.exists(elo_csv_path):
    pd.DataFrame({
        "team_code": ["GER", "ARG", "FRA"],
        "team_name": ["Deutschland", "Argentinien", "Frankreich"],
        "elo_rating": [1980, 2140, 2090]
    }).to_csv(elo_csv_path, index=False)

try:
    _elo_doc = cache_collection.find_one({"_id": "elo_ratings"})
    if _elo_doc and _elo_doc.get("rows"):
        pd.DataFrame(_elo_doc["rows"]).to_csv(elo_csv_path, index=False)
        logger.info("Startup: restored elo_ratings.csv from MongoDB")
    _hist_doc = cache_collection.find_one({"_id": "elo_history"})
    if _hist_doc and _hist_doc.get("data"):
        _hist_path = os.path.join(_data_dir, 'elo_history.json')
        with open(_hist_path, 'w', encoding='utf-8') as _hf:
            json.dump(_hist_doc["data"], _hf, indent=4)
        logger.info("Startup: restored elo_history.json from MongoDB")
    _proc_doc = cache_collection.find_one({"_id": "processed_match_ids"})
    if _proc_doc and _proc_doc.get("ids") is not None:
        _proc_path = os.path.join(_data_dir, 'processed_matches.json')
        with open(_proc_path, 'w', encoding='utf-8') as _pf:
            json.dump(_proc_doc["ids"], _pf)
        logger.info(f"Startup: restored {len(_proc_doc['ids'])} processed match IDs from MongoDB")
except Exception as _e:
    logger.warning(f"Startup: MongoDB restore skipped — {_e}")

math_engine = MathEngine(elo_csv_path, TEAM_MAPPING)
global_odds_engine = OddsApiEngine()
scores_cache_path = os.path.join(_data_dir, 'scores_cache.json')

# ── Wire routers ─────────────────────────────────────────────
app.include_router(matches_router(math_engine, global_odds_engine, cache_collection, archive_collection))
app.include_router(predict_router(math_engine, global_odds_engine, cache_collection, limiter))
app.include_router(custom_bot_router(math_engine, archive_collection, custom_bot_collection, limiter))
app.include_router(simulate_router(math_engine, cache_collection))

# ── Small endpoints (not worth extracting) ───────────────────

@app.get("/api/ping")
def ping():
    """Lightweight keep-alive endpoint — call every 5 min to prevent Render cold starts."""
    return {"ok": True}


@app.get("/api/quota")
def get_quota():
    return {"odds": read_quota("odds"), "football": read_quota("football")}


@app.post("/api/archive/user_tip")
@limiter.limit("30/minute")
def set_user_tip(request: Request, payload: dict):
    match_id  = payload.get("match_id")
    user_tip  = payload.get("user_tip", "").strip()

    if not match_id or not user_tip:
        raise HTTPException(status_code=400, detail="match_id and user_tip required")

    parts = user_tip.split(":")
    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        raise HTTPException(status_code=400, detail="user_tip must be in format H:A (e.g. 2:1)")

    doc = archive_collection.find_one({"_id": match_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Match not in archive")

    entry = {k: v for k, v in doc.items() if k != "_id"}
    entry["prediction"]["user_tip"] = user_tip

    actual = entry["post_match_result"].get("actual_score")
    if actual:
        is_ko = entry["metadata"].get("is_ko_phase", False)
        pts = MathEngine.calculate_actual_points(user_tip, actual, is_ko)
        entry["post_match_result"]["points_earned"] = pts
    else:
        pts = None

    upsert_archive_entry(archive_collection, match_id, entry)
    return {"ok": True, "points_earned": pts}

@app.get("/api/archive")
def get_archive():
    return load_archive_from_db(archive_collection)

@app.get("/api/standings")
def get_standings():
    try:
        doc = cache_collection.find_one({"_id": "standings_cache"})
        if doc and doc.get("data"):
            return doc["data"]
    except Exception:
        pass
    return []

@app.get("/api/elo_history")
def get_elo_history():
    try:
        doc = cache_collection.find_one({"_id": "elo_history"})
        if doc and doc.get("data"):
            return doc["data"]
    except Exception:
        pass
    history_path = os.path.join(_data_dir, 'elo_history.json')
    if os.path.exists(history_path):
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {}

@app.get("/api/elo_ratings")
def get_elo_ratings():
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'elo_ratings.csv')
    out = {}
    try:
        import csv as _csv
        with open(csv_path, 'r', encoding='utf-8') as f:
            for row in _csv.DictReader(f):
                try:
                    out[row['team_name']] = {
                        'team_code': row.get('team_code', ''),
                        'elo': float(row['elo_rating']),
                    }
                except (ValueError, KeyError):
                    continue
    except FileNotFoundError:
        pass
    return out

@app.get("/api/recalculate_points")
def recalculate_all_points():
    archive = load_archive_from_db(archive_collection)
    updated = 0
    for match_id, entry in archive.items():
        if entry.get("post_match_result", {}).get("status") == "completed":
            actual_score = entry.get("post_match_result", {}).get("actual_score")
            algo_tip = entry.get("prediction", {}).get("top_tip")
            is_ko = entry.get("metadata", {}).get("is_ko_phase", False)

            if actual_score and algo_tip:
                old_algo_pts = entry.get("post_match_result", {}).get("algo_points")
                new_algo_pts = MathEngine.calculate_actual_points(algo_tip, actual_score, is_ko)

                if old_algo_pts != new_algo_pts:
                    entry["post_match_result"]["algo_points"] = new_algo_pts
                    updated += 1

                    bots = entry.get("prediction", {}).get("bots", {})
                    if bots:
                        entry["post_match_result"]["bot_points"] = {
                            bot: MathEngine.calculate_actual_points(info["tip"], actual_score, is_ko)
                            for bot, info in bots.items() if info.get("tip")
                        }

                    upsert_archive_entry(archive_collection, match_id, entry)

    return {"status": "success", "recalculated": updated}


@app.get("/api/rebuild_honest_tips")
def rebuild_honest_tips():
    """One-off repair: recompute every completed match's algo tip from its
    pre_match_snapshot (odds + Elo captured BEFORE kickoff) using the exact
    dashboard pipeline. Removes any hindsight tips that leaked into the
    archive, then regrades algo_points from the honest tip."""
    import numpy as np
    archive = load_archive_from_db(archive_collection)
    rebuilt = skipped = 0
    for match_id, entry in archive.items():
        if entry.get("post_match_result", {}).get("status") != "completed":
            continue
        snap = entry.get("pre_match_snapshot") or {}
        odds = snap.get("odds") or {}
        elo = snap.get("elo_state") or {}
        if not all(k in odds for k in ("home", "draw", "away")) or \
           "home_rating" not in elo or "away_rating" not in elo:
            skipped += 1
            continue

        try:
            true_probs = MathEngine.remove_margin(odds["home"], odds["draw"], odds["away"])
            # Same blend as the dashboard: no host bonus (odds already price it in).
            elo_home_share = math_engine.get_elo_probability(elo["home_rating"], elo["away_rating"])
            elo_away_share = 1.0 - elo_home_share
            pool = true_probs["home"] + true_probs["away"]
            prob_home = (true_probs["home"] / pool * 0.7 + elo_home_share * 0.3) * pool
            prob_away = (true_probs["away"] / pool * 0.7 + elo_away_share * 0.3) * pool
            prob_draw = true_probs["draw"]

            if "over25" in odds and "under25" in odds:
                raw_over, raw_under = 1.0 / odds["over25"], 1.0 / odds["under25"]
                prob_over25 = raw_over / (raw_over + raw_under)
            else:
                prob_over25 = None

            is_ko = entry.get("metadata", {}).get("is_ko_phase", False)
            xg_h, xg_a = math_engine.derive_xg_from_odds(prob_home, prob_draw, prob_away, prob_over25)
            if is_ko:
                base = math_engine.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
                et_factor = 1 + float(np.sum(np.diag(base.values))) / 3
                xg_h *= et_factor
                xg_a *= et_factor
            sm = math_engine.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
            df_xp = math_engine.calculate_expected_points(sm, is_ko_phase=is_ko)
            if df_xp.empty:
                skipped += 1
                continue

            tip = df_xp.iloc[0]["Tipp"]
            entry["prediction"]["top_tip"] = tip
            entry["prediction"]["max_xp"] = float(df_xp.iloc[0]["xP"])
            entry["prediction"]["algo_reconstructed"] = False
            entry["prediction"]["tip_source"] = "pre_match_snapshot"

            actual = entry.get("post_match_result", {}).get("actual_score")
            if actual:
                entry["post_match_result"]["algo_points"] = \
                    MathEngine.calculate_actual_points(tip, actual, is_ko)

            upsert_archive_entry(archive_collection, match_id, entry)
            rebuilt += 1
        except Exception as e:
            logger.warning(f"rebuild_honest_tips failed for {match_id}: {e}")
            skipped += 1

    return {"status": "success", "rebuilt": rebuilt, "skipped": skipped}


@app.get("/api/sync_elo")
@limiter.limit("5/hour")
def sync_elo(request: Request, force: bool = False):
    try:
        return perform_elo_sync(
            math_engine=math_engine,
            odds_engine=global_odds_engine,
            cache_collection=cache_collection,
            archive_collection=archive_collection,
            data_dir=_data_dir,
            scores_cache_path=scores_cache_path,
            MathEngine=MathEngine,
            force=force,
        )
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred processing your request")

# v2 (React/Vite build) is the live frontend; legacy frontend/ stays in the
# repo as fallback — flip the path back to '..', 'frontend' to roll back.
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend-v2', 'dist'))
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
