import os
import sys
import logging

import pandas as pd
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
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
from src.routes.matches import init_matches_router
from src.routes.predict import init_predict_router

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
    return response

# ── Team name normalization ──────────────────────────────────
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
    "United States": "USA", "USA": "USA",
    "South Korea": "South Korea", "Korea Republic": "South Korea",
    "Iran": "Iran", "IR Iran": "Iran",
    "Czech Republic": "Czech Republic", "Czechia": "Czech Republic",
    "Ivory Coast": "Ivory Coast", "Côte d'Ivoire": "Ivory Coast",
}

# ── Engine init ──────────────────────────────────────────────
elo_csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'elo_ratings.csv')
if not os.path.exists(elo_csv_path):
    os.makedirs(os.path.dirname(elo_csv_path), exist_ok=True)
    pd.DataFrame({
        "team_code": ["GER", "ARG", "FRA"],
        "team_name": ["Deutschland", "Argentinien", "Frankreich"],
        "elo_rating": [1980, 2140, 2090]
    }).to_csv(elo_csv_path, index=False)

math_engine = MathEngine(elo_csv_path, TEAM_MAPPING)
global_odds_engine = OddsApiEngine()
scores_cache_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'scores_cache.json')

# ── Route registration ───────────────────────────────────────
app.include_router(init_matches_router(
    math_engine=math_engine,
    global_odds_engine=global_odds_engine,
    odds_engine_cls=OddsApiEngine,
    archive_collection=archive_collection,
    cache_collection=cache_collection,
    team_mapping=TEAM_MAPPING,
    display_mapping=DISPLAY_MAPPING,
    scores_cache_path=scores_cache_path,
    limiter=limiter,
))

app.include_router(init_predict_router(
    math_engine=math_engine,
    global_odds_engine=global_odds_engine,
    archive_collection=archive_collection,
    cache_collection=cache_collection,
    custom_bot_collection=custom_bot_collection,
    team_mapping=TEAM_MAPPING,
    display_mapping=DISPLAY_MAPPING,
    limiter=limiter,
))

# ── Static files (must be last) ─────────────────────────────
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
