import os
import sys
import json
import time
import statistics
import logging
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pymongo import MongoClient
import certifi
from slowapi import Limiter
from slowapi.util import get_remote_address

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

# Engine switch: set USE_API_FOOTBALL=true in .env when the Odds-API quota is
# exhausted. The API-Football engine normalizes responses to the legacy
# Odds-API shape, so the rest of api.py needs no changes.
if os.getenv("USE_API_FOOTBALL", "").lower() in ("1", "true", "yes"):
    from src.odds_engine_apifootball import OddsApiEngine
    print("Odds engine: API-Football (api-sports.io)")
else:
    from src.odds_engine import OddsApiEngine
    print("Odds engine: The Odds API")

from src.math_engine import MathEngine

app = FastAPI(title="WM 2026 Predictor API")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── MongoDB setup ─────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable is required. Set it in your .env file.")
_mongo_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
_db = _mongo_client["wm2026_db"]
archive_collection = _db["archive"]
cache_collection = _db["cache"]
custom_bot_collection = _db["custom_bot"]

# ── CORS ──────────────────────────────────────────────────────
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

limiter = Limiter(key_func=get_remote_address)
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
global_odds_engine = OddsApiEngine()

# File paths for data that remains file-based (out of scope for MongoDB migration)
scores_cache_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'scores_cache.json')

TOTALS_CACHE_TTL = 3600   # 1h per match
SCORES_CACHE_TTL = 1800   # 30 min — avoids burning quota on repeated manual syncs


# ── MongoDB helpers ───────────────────────────────────────────

def _load_archive_from_db() -> dict:
    """Load the full prediction archive from MongoDB as a {match_id: entry} dict."""
    result = {}
    try:
        for doc in archive_collection.find():
            mid = doc["_id"]
            result[mid] = {k: v for k, v in doc.items() if k != "_id"}
    except Exception as e:
        logger.error(f"Failed to load archive from MongoDB: {e}")
    return result

def _upsert_archive_entry(match_id: str, entry: dict) -> None:
    """Upsert a single archive entry into MongoDB."""
    archive_collection.replace_one(
        {"_id": match_id},
        {"_id": match_id, **entry},
        upsert=True
    )


# ── Core helpers ──────────────────────────────────────────────

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
    cache_key = f"totals_{event_id}"
    entry = {}
    try:
        doc = cache_collection.find_one({"_id": cache_key})
        if doc:
            entry = doc
    except Exception:
        pass

    if entry and (time.time() - entry.get("timestamp", 0) < TOTALS_CACHE_TTL):
        totals_bookmakers = entry.get("bookmakers", [])
    else:
        try:
            engine = OddsApiEngine()
            event_data = engine.get_event_odds(event_id, market="totals")
            totals_bookmakers = event_data.get("bookmakers", [])
            cache_collection.update_one(
                {"_id": cache_key},
                {"$set": {"timestamp": time.time(), "bookmakers": totals_bookmakers}},
                upsert=True
            )
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

def _enrich_edge(matches: list) -> list:
    """
    Berechnet die Edge (Elo vs Markt im Sieg/Niederlage-Pool) aus den bereits
    vorhandenen Quoten — kostet KEINEN API-Request. Idempotent: nur fehlende
    Werte werden ergänzt.
    """
    for m in matches:
        home_norm = TEAM_MAPPING.get(m.get("home_team"), m.get("home_team"))
        away_norm = TEAM_MAPPING.get(m.get("away_team"), m.get("away_team"))
        m["home_form"] = math_engine.team_forms.get(home_norm, {"form": [], "on_fire": False})
        m["away_form"] = math_engine.team_forms.get(away_norm, {"form": [], "on_fire": False})

        # Inject API-Football H2H and Lineup Diffs
        if hasattr(global_odds_engine, "get_h2h"):
            try:
                home_id = m.get("home_team_id")
                away_id = m.get("away_team_id")
                if home_id and away_id:
                    m["h2h"] = global_odds_engine.get_h2h(home_id, away_id)

                fixture_id = m.get("id")
                commence = m.get("commence_time") or m.get("raw_match", {}).get("commence_time")
                if fixture_id and commence:
                    m["lineup_diff"] = global_odds_engine.get_lineup(fixture_id, commence)
            except Exception:
                pass

        if m.get("edge_home") is not None:
            continue
        odds = m.get("odds", {})
        if not all(k in odds for k in ("home", "draw", "away")):
            continue
        try:
            true_probs = MathEngine.remove_margin(odds["home"], odds["draw"], odds["away"])
            pool = true_probs["home"] + true_probs["away"]
            market_home_share = (true_probs["home"] / pool) if pool > 0 else 0.5
            elo_home_share, _ = math_engine.get_match_elo_probabilities(m.get("home_team"), m.get("away_team"))
            m["elo_home_share"] = elo_home_share
            m["market_home_share"] = market_home_share
            m["edge_home"] = elo_home_share - market_home_share
        except Exception:
            pass
    return matches


# ── Endpoints ─────────────────────────────────────────────────

@app.get("/api/quota")
def get_quota():
    """Return both providers' quota so the sidebar can show each.
    odds   -> The Odds API   (data/api_quota_odds.json)
    football-> API-Football  (data/api_quota.json)
    """
    base = os.path.join(os.path.dirname(__file__), '..', 'data')

    def _load(fname):
        try:
            with open(os.path.join(base, fname), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"remaining": "--", "used": "?"}

    return {"odds": _load('api_quota_odds.json'), "football": _load('api_quota.json')}


@app.get("/api/matches")
def get_matches(force: bool = False):
    """
    Holt die Spiele. Nutzt den Cache, es sei denn, force=True wird übergeben.
    """
    archive = _load_archive_from_db()
    math_engine.reload_elo_data(archive=archive)

    # 1. Cache prüfen — TTL is dynamic based on soonest kickoff time
    if not force:
        try:
            cached = cache_collection.find_one({"_id": "matches_cache"})
            if cached:
                timestamp = cached.get("timestamp", 0)
                data = cached.get("data")
                if data is not None:
                    ttl = _dynamic_ttl(data)
                    if time.time() - timestamp < ttl:
                        return _enrich_edge(data)
        except Exception:
            pass

    # 2. API Call — h2h only (1 request). Totals are fetched lazily per match on /api/predict.
    engine = OddsApiEngine()
    data = engine.get_world_cup_odds(market="h2h")

    results = []
    _bot_inputs = {}  # match_id -> {score_matrix, true_probs, prob_over25} — not saved to cache
    for m in data:
        home_raw = m.get("home_team")
        away_raw = m.get("away_team")
        try:
            event_id = m.get("id", "")
            # Merge cached totals using the same code path as /api/predict so
            # top_tip in the fixture list always matches the detail view.
            m = _fetch_or_cache_totals(event_id, m)
            odds = extract_odds(m)

            try:
                math_engine.ensure_teams_exist(
                    TEAM_MAPPING.get(home_raw, home_raw),
                    TEAM_MAPPING.get(away_raw, away_raw),
                )
                true_probs = MathEngine.remove_margin(odds["home"], odds["draw"], odds["away"])

                # Elo-Blend (identisch zu /api/predict) damit top_tip auf der
                # Fixture-Liste mit dem Detail-View übereinstimmt.
                elo_home_share, elo_away_share = math_engine.get_match_elo_probabilities(home_raw, away_raw)
                win_loss_pool = true_probs["home"] + true_probs["away"]
                prob_home = (true_probs["home"] / win_loss_pool * 0.7 + elo_home_share * 0.3) * win_loss_pool
                prob_away = (true_probs["away"] / win_loss_pool * 0.7 + elo_away_share * 0.3) * win_loss_pool
                prob_draw = true_probs["draw"]

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

                market_home_share = (true_probs["home"] / win_loss_pool) if win_loss_pool > 0 else 0.5
                edge_home = elo_home_share - market_home_share

                # Store inputs for bot computation in archive section (not cached)
                if event_id and top_tip != "N/A":
                    _bot_inputs[event_id] = {
                        "score_matrix": sm,
                        "base_xp_df": df_xp,
                        "true_probs": true_probs,
                        "prob_over25": prob_over25,
                    }
            except Exception:
                top_tip = "N/A"
                max_xp = 0.0
                elo_home_share = None
                market_home_share = None
                edge_home = None

            results.append({
                "id": m.get("id"),
                "home_team": home_raw,
                "away_team": away_raw,
                "home_disp": DISPLAY_MAPPING.get(home_raw, home_raw),
                "away_disp": DISPLAY_MAPPING.get(away_raw, away_raw),
                "odds": odds,
                "top_tip": top_tip,
                "max_xp": max_xp,
                "elo_home_share": elo_home_share,
                "market_home_share": market_home_share,
                "edge_home": edge_home,
                "raw_match": m
            })
        except ValueError:
            continue

    # 3. Cache aktualisieren — merge with existing so completed matches aren't lost
    try:
        existing_matches = {}
        try:
            cached = cache_collection.find_one({"_id": "matches_cache"})
            if cached:
                existing_matches = {m["id"]: m for m in cached.get("data", [])}
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
                # Backfill: alte Cache-Einträge ohne Edge-Daten einmalig nachziehen
                missing_edge = "edge_home" not in prev and r.get("edge_home") is not None
                if not odds_changed and not missing_edge:
                    continue  # keep old entry unchanged
            existing_matches[r["id"]] = r
        merged = sorted(existing_matches.values(), key=lambda m: m.get("raw_match", {}).get("commence_time", ""))
        cache_collection.update_one(
            {"_id": "matches_cache"},
            {"$set": {"timestamp": time.time(), "data": merged}},
            upsert=True
        )
    except Exception as e:
        print(f"Fehler beim Speichern des Caches: {e}")

    # 4. Archive: log new pre-match snapshots (only first time a match_id is seen)
    #    Also backfill bots for existing entries that predate this feature.
    try:
        changed_entries = {}
        for r in results:
            if r["top_tip"] == "N/A":
                continue

            bot_in = _bot_inputs.get(r["id"])
            bots = None
            if bot_in:
                try:
                    bots = math_engine.compute_bot_tips(
                        score_matrix=bot_in["score_matrix"],
                        base_xp_df=bot_in["base_xp_df"],
                        true_probs=bot_in["true_probs"],
                        prob_over25=bot_in["prob_over25"],
                        home_team=r["home_team"],
                        away_team=r["away_team"],
                        match_id=r["id"],
                        is_ko_phase=False
                    )
                except Exception as e:
                    print(f"Bot tips failed for {r['id']}: {e}")

            if r["id"] not in archive:
                # New entry
                home_norm = TEAM_MAPPING.get(r["home_team"], r["home_team"])
                away_norm = TEAM_MAPPING.get(r["away_team"], r["away_team"])
                elo_rows_home = math_engine.elo_df.loc[math_engine.elo_df['team_name'] == home_norm, 'elo_rating']
                elo_rows_away = math_engine.elo_df.loc[math_engine.elo_df['team_name'] == away_norm, 'elo_rating']
                elo_home_val = float(elo_rows_home.values[0]) if not elo_rows_home.empty else 1500.0
                elo_away_val = float(elo_rows_away.values[0]) if not elo_rows_away.empty else 1500.0

                new_entry = {
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
                        "user_tip": None,
                        "max_xp": float(r["max_xp"]),
                        "bots": bots or {},
                    },
                    "post_match_result": {
                        "status": "pending",
                        "actual_score": None,
                        "points_earned": None,
                        "algo_points": None,
                        "bot_points": {k: None for k in (bots or {})},
                    }
                }
                archive[r["id"]] = new_entry
                changed_entries[r["id"]] = new_entry
            elif bots and "bots" not in archive[r["id"]].get("prediction", {}):
                # Backfill bots for existing entry that predates this feature
                archive[r["id"]]["prediction"]["bots"] = bots
                pmr = archive[r["id"]]["post_match_result"]
                if "bot_points" not in pmr:
                    actual = pmr.get("actual_score")
                    is_ko = archive[r["id"]]["metadata"].get("is_ko_phase", False)
                    if actual:
                        pmr["bot_points"] = {
                            bot: MathEngine.calculate_actual_points(info["tip"], actual, is_ko)
                            for bot, info in bots.items() if info.get("tip")
                        }
                    else:
                        pmr["bot_points"] = {k: None for k in bots}
                changed_entries[r["id"]] = archive[r["id"]]

        for mid, entry in changed_entries.items():
            _upsert_archive_entry(mid, entry)
    except Exception as e:
        print(f"Archive logging failed: {e}")

    return results

@app.post("/api/predict")
@limiter.limit("20/minute")
def predict_match(request: Request, payload: dict):
    math_engine.reload_elo_data()
    match_data = payload.get("match")
    is_ko = payload.get("is_ko", False)
    home_resting = payload.get("home_resting", False)
    away_resting = payload.get("away_resting", False)

    if not match_data:
        raise HTTPException(status_code=400, detail="Match data required")

    try:
        event_id = match_data.get("id", "")
        match_data = _fetch_or_cache_totals(event_id, match_data)

        math_engine.ensure_teams_exist(
            TEAM_MAPPING.get(match_data.get("home_team"), match_data.get("home_team")),
            TEAM_MAPPING.get(match_data.get("away_team"), match_data.get("away_team")),
        )
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
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred processing your request")

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

    _upsert_archive_entry(match_id, entry)
    return {"ok": True, "points_earned": pts}

@app.get("/api/archive")
def get_archive():
    return _load_archive_from_db()

# ── Build-a-Bot: user-designed strategy ───────────────────────
_CUSTOM_BOT_ID = "default"

def _clean_bot_params(params: dict) -> dict:
    """Coerce + clamp the four strategy knobs to safe ranges."""
    def clamp(v, lo, hi, default):
        try:
            return max(lo, min(hi, float(v)))
        except (TypeError, ValueError):
            return default
    return {
        "market_weight": clamp(params.get("market_weight"), 0.0, 1.0, 0.7),
        "risk":          clamp(params.get("risk"), -1.0, 1.0, 0.0),
        "draw_bias":     clamp(params.get("draw_bias"), 0.0, 6.0, 0.0),
        "underdog_bias": clamp(params.get("underdog_bias"), 0.0, 6.0, 0.0),
    }

@app.post("/api/custom_bot/simulate")
@limiter.limit("60/minute")
def simulate_custom_bot(request: Request, payload: dict):
    """
    Replay a user-designed bot over every completed archive match and report how
    it would have scored. Stateless — nothing is persisted. Reconstructs each tip
    from the stored pre-match odds + Elo ratings, so the bot competes with full
    history the moment it is built.
    """
    params = _clean_bot_params(payload.get("params") or {})
    archive = _load_archive_from_db()
    math_engine.reload_elo_data(archive=archive)

    completed = []
    for mid, match in archive.items():
        pmr = match.get("post_match_result", {})
        if pmr.get("status") != "completed":
            continue
        actual = pmr.get("actual_score")
        snap = match.get("pre_match_snapshot", {})
        odds = snap.get("odds") or {}
        if not actual or not all(k in odds for k in ("home", "draw", "away")):
            continue
        completed.append((mid, match, snap, odds, actual))

    # Chronological — same ordering the bot-race chart uses.
    completed.sort(key=lambda x: x[2].get("timestamp_recorded") or "")

    total = 0
    correct_tendency = 0
    running = 0
    race = []
    breakdown = []
    for mid, match, snap, odds, actual in completed:
        meta = match.get("metadata", {})
        is_ko = meta.get("is_ko_phase", False)
        elo_state = snap.get("elo_state") or {}
        elo_home = elo_state.get("home_rating", 1500.0)
        elo_away = elo_state.get("away_rating", 1500.0)
        try:
            tip = math_engine.compute_custom_bot_tip(odds, elo_home, elo_away, params, is_ko)
            pts = MathEngine.calculate_actual_points(tip, actual, is_ko)
        except Exception as e:
            logger.error(f"Custom-bot sim failed for {mid}: {e}")
            continue
        total += pts
        if pts >= 5:
            correct_tendency += 1
        running += pts
        label = f"{(meta.get('home_team', '') or '')[:3].upper()}–{(meta.get('away_team', '') or '')[:3].upper()}"
        race.append({"label": label, "cumulative": running})
        breakdown.append({
            "match_id": mid,
            "home_disp": meta.get("home_disp"),
            "away_disp": meta.get("away_disp"),
            "actual": actual,
            "tip": tip,
            "points": pts,
        })

    n = len(breakdown)
    return {
        "params": params,
        "total_points": total,
        "matches": n,
        "tendency_rate": (correct_tendency / n) if n else 0.0,
        "race": race,
        "breakdown": breakdown,
    }

@app.get("/api/custom_bot")
def get_custom_bot():
    """Return the saved build-a-bot config, or exists=False if none saved yet."""
    doc = custom_bot_collection.find_one({"_id": _CUSTOM_BOT_ID})
    if not doc:
        return {"exists": False}
    return {"exists": True, "name": doc.get("name"), "params": doc.get("params", {})}

@app.post("/api/custom_bot")
@limiter.limit("30/minute")
def save_custom_bot(request: Request, payload: dict):
    """Persist the single user-designed bot (name + four knobs)."""
    name = (payload.get("name") or "Mein Bot").strip()[:40] or "Mein Bot"
    params = _clean_bot_params(payload.get("params") or {})
    custom_bot_collection.replace_one(
        {"_id": _CUSTOM_BOT_ID},
        {"_id": _CUSTOM_BOT_ID, "name": name, "params": params},
        upsert=True,
    )
    return {"ok": True, "name": name, "params": params}

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

@app.get("/api/elo_ratings")
def get_elo_ratings():
    """Authoritative current Elo per team — includes teams with no match history yet."""
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

def perform_elo_sync() -> dict:
    print("Elo sync triggered...")
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
            print(f"Elo sync completed: {updates} updates.")

        # Post-match grading: score archived predictions against actual results
        # Also create retroactive entries for completed matches played before the app started
        try:
            archive = _load_archive_from_db()
            changed_entries = {}
            graded = 0
            retro = 0

            for match in completed_matches:
                match_id = match.get("id")
                if not match_id or not match.get("completed"):
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

                if match_id not in archive:
                    # Match was played before this app started tracking — create a retroactive entry
                    new_entry = {
                        "metadata": {
                            "home_team": home_team,
                            "away_team": away_team,
                            "home_disp": DISPLAY_MAPPING.get(home_team, home_team),
                            "away_disp": DISPLAY_MAPPING.get(away_team, away_team),
                            "is_ko_phase": False
                        },
                        "pre_match_snapshot": None,
                        "prediction": {"top_tip": None, "max_xp": None},
                        "post_match_result": {
                            "status": "completed",
                            "actual_score": actual_score_str,
                            "points_earned": None
                        }
                    }
                    archive[match_id] = new_entry
                    changed_entries[match_id] = new_entry
                    retro += 1
                    continue

                if archive[match_id]["post_match_result"]["status"] != "pending":
                    continue

                algo_tip  = archive[match_id]["prediction"].get("top_tip")
                user_tip  = archive[match_id]["prediction"].get("user_tip")
                is_ko     = archive[match_id]["metadata"]["is_ko_phase"]
                active_tip = user_tip if user_tip else algo_tip
                archive[match_id]["post_match_result"]["status"]        = "completed"
                archive[match_id]["post_match_result"]["actual_score"]  = actual_score_str
                archive[match_id]["post_match_result"]["points_earned"] = (
                    MathEngine.calculate_actual_points(active_tip, actual_score_str, is_ko)
                    if active_tip else None
                )
                archive[match_id]["post_match_result"]["algo_points"] = (
                    MathEngine.calculate_actual_points(algo_tip, actual_score_str, is_ko)
                    if algo_tip else None
                )
                bots = archive[match_id]["prediction"].get("bots", {})
                if bots:
                    archive[match_id]["post_match_result"]["bot_points"] = {
                        bot: MathEngine.calculate_actual_points(info["tip"], actual_score_str, is_ko)
                        for bot, info in bots.items() if info.get("tip")
                    }
                changed_entries[match_id] = archive[match_id]
                graded += 1

            # Reconstruction: Algo-Tipps für completed Einträge ohne pre_match_snapshot
            # aus der Elo-only-Pipeline ableiten (z. B. Matches vor App-Start).
            ct_map = {m.get('id'): m.get('commence_time') for m in completed_matches}
            reconstructed = 0
            for mid, entry in archive.items():
                if entry.get('post_match_result', {}).get('status') != 'completed':
                    continue
                if entry.get('pre_match_snapshot') is not None:
                    continue
                actual = entry.get('post_match_result', {}).get('actual_score')
                if not actual:
                    continue

                home = entry['metadata']['home_team']
                away = entry['metadata']['away_team']
                is_ko_match = entry['metadata'].get('is_ko_phase', False)

                bots = math_engine.reconstruct_bot_tips(
                    home, away, str(mid), commence_time=ct_map.get(mid), is_ko=is_ko_match
                )
                if not bots:
                    continue
                tip = bots["professor"]["tip"]
                max_xp = bots["professor"].get("xp", 0)
                if not tip:
                    continue

                # Idempotenz: skip wenn Tipp + Flag + Bots schon korrekt
                already_done = (
                    entry['prediction'].get('top_tip') == tip
                    and entry['prediction'].get('algo_reconstructed') is True
                    and entry['prediction'].get('bots')
                )
                if already_done:
                    continue

                entry['prediction']['top_tip'] = tip
                entry['prediction']['max_xp'] = max_xp
                entry['prediction']['algo_reconstructed'] = True
                entry['prediction']['bots'] = bots
                entry['post_match_result']['algo_points'] = MathEngine.calculate_actual_points(
                    tip, actual, is_ko_match
                )
                entry['post_match_result']['bot_points'] = {
                    name: MathEngine.calculate_actual_points(info["tip"], actual, is_ko_match)
                    for name, info in bots.items() if info.get("tip")
                }
                user_tip = entry['prediction'].get('user_tip')
                if user_tip:
                    entry['post_match_result']['points_earned'] = MathEngine.calculate_actual_points(
                        user_tip, actual, is_ko_match
                    )
                changed_entries[mid] = entry
                reconstructed += 1

            for mid, entry in changed_entries.items():
                _upsert_archive_entry(mid, entry)

            if graded:
                print(f"Archive grading completed: {graded} predictions scored.")
            if retro:
                print(f"Retroactive archive entries created: {retro} matches.")
            if reconstructed:
                print(f"Algo tips reconstructed: {reconstructed} matches (Elo-only pipeline).")
        except Exception as e:
            print(f"Archive grading failed: {e}")

        if updates > 0:
            return {"status": "success", "updates": updates}
        else:
            print("Elo sync completed: No new matches.")
            return {"status": "info", "message": "No new matches."}
    except Exception as e:
        print(f"Elo sync failed: {str(e)}")
        raise e

@app.get("/api/sync_elo")
@limiter.limit("5/hour")
def sync_elo(request: Request):
    try:
        return perform_elo_sync()
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred processing your request")

frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
