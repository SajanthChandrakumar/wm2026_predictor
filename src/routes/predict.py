import os
import json
import time
import statistics
import logging

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter

from src.math_engine import MathEngine
from src.services.archive import load_archive_from_db, upsert_archive_entry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def init_predict_router(
    math_engine: MathEngine,
    global_odds_engine,
    archive_collection,
    cache_collection,
    custom_bot_collection,
    team_mapping: dict,
    display_mapping: dict,
    limiter: Limiter,
):
    """Wire up dependencies and return the configured router."""

    TOTALS_CACHE_TTL = 3600

    def extract_odds(match):
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

    def _fetch_or_cache_totals(event_id: str, raw_match: dict) -> dict:
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
                event_data = global_odds_engine.get_event_odds(event_id, market="totals")
                totals_bookmakers = event_data.get("bookmakers", [])
                cache_collection.update_one(
                    {"_id": cache_key},
                    {"$set": {"timestamp": time.time(), "bookmakers": totals_bookmakers}},
                    upsert=True
                )
            except Exception as e:
                logger.warning(f"Totals fetch failed for {event_id}: {e}")
                totals_bookmakers = []

        if not totals_bookmakers:
            return raw_match

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

    def _clean_bot_params(params: dict) -> dict:
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

    _CUSTOM_BOT_ID = "default"

    @router.post("/predict")
    @limiter.limit("20/minute")
    def predict_match(request: Request, payload: dict):
        math_engine.reload_elo_data()
        match_data = payload.get("match")
        is_ko = payload.get("is_ko", False)

        if not match_data:
            raise HTTPException(status_code=400, detail="Match data required")

        try:
            event_id = match_data.get("id", "")
            match_data = _fetch_or_cache_totals(event_id, match_data)

            math_engine.ensure_teams_exist(
                team_mapping.get(match_data.get("home_team"), match_data.get("home_team")),
                team_mapping.get(match_data.get("away_team"), match_data.get("away_team")),
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
            )

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

    @router.post("/archive/user_tip")
    @limiter.limit("30/minute")
    def set_user_tip(request: Request, payload: dict):
        match_id = payload.get("match_id")
        user_tip = payload.get("user_tip", "").strip()

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

    @router.get("/archive")
    def get_archive():
        return load_archive_from_db(archive_collection)

    @router.post("/custom_bot/simulate")
    @limiter.limit("60/minute")
    def simulate_custom_bot(request: Request, payload: dict):
        params = _clean_bot_params(payload.get("params") or {})
        archive = load_archive_from_db(archive_collection)
        math_engine.reload_elo_data(archive=archive)

        completed = []
        for mid, match in archive.items():
            pmr = match.get("post_match_result", {})
            if pmr.get("status") != "completed":
                continue
            actual = pmr.get("actual_score")
            snap = match.get("pre_match_snapshot") or {}
            odds = snap.get("odds") or {}
            if not actual or not all(k in odds for k in ("home", "draw", "away")):
                continue
            completed.append((mid, match, snap, odds, actual))

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

    @router.get("/custom_bot")
    def get_custom_bot():
        doc = custom_bot_collection.find_one({"_id": _CUSTOM_BOT_ID})
        if not doc:
            return {"exists": False}
        return {"exists": True, "name": doc.get("name"), "params": doc.get("params", {})}

    @router.post("/custom_bot")
    @limiter.limit("30/minute")
    def save_custom_bot(request: Request, payload: dict):
        name = (payload.get("name") or "Mein Bot").strip()[:40] or "Mein Bot"
        params = _clean_bot_params(payload.get("params") or {})
        custom_bot_collection.replace_one(
            {"_id": _CUSTOM_BOT_ID},
            {"_id": _CUSTOM_BOT_ID, "name": name, "params": params},
            upsert=True,
        )
        return {"ok": True, "name": name, "params": params}

    @router.get("/quota")
    def get_quota():
        base = os.path.join(os.path.dirname(math_engine.elo_csv_path), '..')
        def _load(fname):
            try:
                with open(os.path.join(base, 'data', fname), 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {"remaining": "--", "used": "?"}
        return {"odds": _load('api_quota_odds.json'), "football": _load('api_quota.json')}

    return router
