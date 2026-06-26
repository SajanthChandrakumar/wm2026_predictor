import os
import json
import time
import statistics
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter

from src.math_engine import MathEngine
from src.services.archive import load_archive_from_db, upsert_archive_entry
from src.services.elo_sync import perform_elo_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def init_matches_router(
    math_engine: MathEngine,
    global_odds_engine,
    odds_engine_cls,
    archive_collection,
    cache_collection,
    team_mapping: dict,
    display_mapping: dict,
    scores_cache_path: str,
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

    def _dynamic_ttl(matches: list) -> int:
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
        if soonest > 86400:
            return 43200
        if soonest > 7200:
            return 3600
        return 900

    def _fetch_or_cache_totals(event_id: str, raw_match: dict, fetch_if_missing: bool = True) -> dict:
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
        elif fetch_if_missing:
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
        else:
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

    def _enrich_edge(matches: list) -> list:
        for m in matches:
            home_norm = team_mapping.get(m.get("home_team"), m.get("home_team"))
            away_norm = team_mapping.get(m.get("away_team"), m.get("away_team"))
            m["home_form"] = math_engine.team_forms.get(home_norm, {"form": [], "on_fire": False})
            m["away_form"] = math_engine.team_forms.get(away_norm, {"form": [], "on_fire": False})

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

    @router.get("/matches")
    def get_matches(force: bool = False):
        archive = load_archive_from_db(archive_collection)
        math_engine.reload_elo_data(archive=archive)

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

        try:
            data = global_odds_engine.get_world_cup_odds(market="h2h")
        except Exception as e:
            try:
                cached = cache_collection.find_one({"_id": "matches_cache"})
                if cached and cached.get("data"):
                    logger.warning(f"Odds API unavailable, serving stale cache: {e}")
                    return _enrich_edge(cached["data"])
            except Exception:
                pass
            raise HTTPException(status_code=503, detail=f"Odds API unavailable: {e}")

        results = []
        _bot_inputs = {}
        for m in data:
            home_raw = m.get("home_team")
            away_raw = m.get("away_team")
            try:
                event_id = m.get("id", "")
                m = _fetch_or_cache_totals(event_id, m, fetch_if_missing=False)
                odds = extract_odds(m)

                try:
                    math_engine.ensure_teams_exist(
                        team_mapping.get(home_raw, home_raw),
                        team_mapping.get(away_raw, away_raw),
                    )
                    true_probs = MathEngine.remove_margin(odds["home"], odds["draw"], odds["away"])

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
                    "home_disp": display_mapping.get(home_raw, home_raw),
                    "away_disp": display_mapping.get(away_raw, away_raw),
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
                    missing_edge = "edge_home" not in prev and r.get("edge_home") is not None
                    if not odds_changed and not missing_edge:
                        continue
                existing_matches[r["id"]] = r
            merged = sorted(existing_matches.values(), key=lambda m: m.get("raw_match", {}).get("commence_time", ""))
            cache_collection.update_one(
                {"_id": "matches_cache"},
                {"$set": {"timestamp": time.time(), "data": merged}},
                upsert=True
            )
        except Exception as e:
            logger.warning(f"Fehler beim Speichern des Caches: {e}")

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
                        logger.warning(f"Bot tips failed for {r['id']}: {e}")

                if r["id"] not in archive:
                    home_norm = team_mapping.get(r["home_team"], r["home_team"])
                    away_norm = team_mapping.get(r["away_team"], r["away_team"])
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
                upsert_archive_entry(archive_collection, mid, entry)
        except Exception as e:
            logger.warning(f"Archive logging failed: {e}")

        for r in results:
            arc = archive.get(r["id"], {})
            r["bots"] = arc.get("prediction", {}).get("bots", {})

        return results

    @router.get("/standings")
    def get_standings():
        try:
            doc = cache_collection.find_one({"_id": "standings_cache"})
            if doc and doc.get("data"):
                return doc["data"]
        except Exception:
            pass
        return []

    @router.get("/elo_history")
    def get_elo_history():
        history_path = os.path.join(os.path.dirname(math_engine.elo_csv_path), 'elo_history.json')
        if os.path.exists(history_path):
            try:
                with open(history_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}

    @router.get("/elo_ratings")
    def get_elo_ratings():
        csv_path = os.path.join(os.path.dirname(math_engine.elo_csv_path), 'elo_ratings.csv')
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

    @router.get("/sync_elo")
    @limiter.limit("5/hour")
    def sync_elo(request: Request):
        try:
            return perform_elo_sync(
                math_engine=math_engine,
                odds_engine_cls=odds_engine_cls,
                archive_collection=archive_collection,
                scores_cache_path=scores_cache_path,
                display_mapping=display_mapping,
            )
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="An error occurred processing your request")

    return router
