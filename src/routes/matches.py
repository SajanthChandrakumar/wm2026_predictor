import time
import logging
from datetime import datetime, timezone, timedelta

import numpy as np
from fastapi import APIRouter, HTTPException

from src.constants import TEAM_MAPPING, DISPLAY_MAPPING, _is_ko_round
from src.services.odds_helpers import extract_odds, dynamic_ttl
from src.services.archive import (
    load_archive_from_db, upsert_archive_entry,
    build_archive_id_index, resolve_archive_id, _canon_team,
)
from src.services import espn_data
from src.math_engine import MathEngine

logger = logging.getLogger(__name__)


def _synth_bookmakers(espn_odds: dict, home_team: str, away_team: str) -> list:
    """Build a single-bookmaker entry (ESPN/DraftKings) in the legacy shape
    extract_odds() expects, used when The Odds API has no match for a fixture."""
    h2h = [
        {"name": home_team, "price": espn_odds["home"]},
        {"name": "Draw", "price": espn_odds["draw"]},
        {"name": away_team, "price": espn_odds["away"]},
    ]
    markets = [{"key": "h2h", "outcomes": h2h}]
    if "over25" in espn_odds and "under25" in espn_odds:
        markets.append({"key": "totals", "outcomes": [
            {"name": "Over", "price": espn_odds["over25"], "point": 2.5},
            {"name": "Under", "price": espn_odds["under25"], "point": 2.5},
        ]})
    return [{"key": "espn_draftkings", "title": "DraftKings (ESPN)", "markets": markets}]


def _build_odds_api_lookup(odds_engine) -> dict:
    """Fetch The Odds API once (h2h+totals) → {(canon_home,canon_away,date): bookmakers}.
    Best-effort: returns {} on any failure so ESPN odds are used instead."""
    try:
        games = odds_engine.get_world_cup_odds(market="h2h,totals")
    except Exception as e:
        print(f"Odds API fetch failed, using ESPN odds only: {e}")
        return {}
    lookup = {}
    for g in games or []:
        h = _canon_team(g.get("home_team", ""))
        a = _canon_team(g.get("away_team", ""))
        date = (g.get("commence_time") or "")[:10]
        if h and a and g.get("bookmakers"):
            lookup[(h, a, date)] = g["bookmakers"]
    return lookup


def _match_odds_api(lookup: dict, home: str, away: str, date: str):
    """Resolve Odds-API bookmakers for a fixture; tolerate ±1 day (UTC edge)."""
    h, a = _canon_team(home), _canon_team(away)
    d = (date or "")[:10]
    if (h, a, d) in lookup:
        return lookup[(h, a, d)]
    try:
        base = datetime.fromisoformat(d)
        for delta in (-1, 1):
            alt = (base + timedelta(days=delta)).strftime("%Y-%m-%d")
            if (h, a, alt) in lookup:
                return lookup[(h, a, alt)]
    except Exception:
        pass
    return None


def _sync_archive_tips(matches, archive, archive_collection):
    """Reconcile dashboard tips with the archive.

    Pending matches: the archive follows the latest recalculation (prediction
    may legitimately shift until kickoff). Completed matches: the archived
    pre-match tip is FROZEN — the dashboard shows it instead of a tip
    recalculated with post-match Elo (that would be hindsight)."""
    changed = {}
    for m in matches:
        mid = m.get("id")
        entry = archive.get(mid)
        if not mid or not entry or not entry.get("prediction"):
            continue

        if entry.get("post_match_result", {}).get("status") == "completed":
            frozen = entry["prediction"].get("top_tip")
            if frozen:
                m["top_tip"] = frozen
                m["max_xp"] = float(entry["prediction"].get("max_xp") or 0)
            continue

        tip = m.get("top_tip")
        if not tip or tip == "N/A":
            continue
        if entry["prediction"].get("top_tip") != tip:
            entry["prediction"]["top_tip"] = tip
            entry["prediction"]["max_xp"] = m.get("max_xp", 0)
            changed[mid] = entry
    for mid, entry in changed.items():
        upsert_archive_entry(archive_collection, mid, entry)
    return matches


def _enrich_edge(matches, math_engine, odds_engine):
    for m in matches:
        # Always recompute — round-keyword logic may have changed since caching.
        m["is_ko_phase"] = _is_ko_round(m.get("raw_match", {}).get("round", ""))

        home_norm = TEAM_MAPPING.get(m.get("home_team"), m.get("home_team"))
        away_norm = TEAM_MAPPING.get(m.get("away_team"), m.get("away_team"))
        m["home_form"] = math_engine.team_forms.get(home_norm, {"form": [], "on_fire": False})
        m["away_form"] = math_engine.team_forms.get(away_norm, {"form": [], "on_fire": False})

        if hasattr(odds_engine, "get_h2h"):
            try:
                if "h2h" not in m:
                    home_id = m.get("home_team_id")
                    away_id = m.get("away_team_id")
                    if home_id and away_id:
                        m["h2h"] = odds_engine.get_h2h(home_id, away_id)

                if "lineup_diff" not in m:
                    fixture_id = m.get("id")
                    commence = m.get("commence_time") or m.get("raw_match", {}).get("commence_time")
                    if fixture_id and commence:
                        m["lineup_diff"] = odds_engine.get_lineup(fixture_id, commence)
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


def init_router(math_engine, odds_engine, cache_collection, archive_collection):
    router = APIRouter(prefix="/api")

    @router.get("/matches")
    def get_matches(force: bool = False):
        # ── Fast path: serve from MongoDB cache without any expensive work ──
        if not force:
            try:
                cached = cache_collection.find_one({"_id": "matches_cache"})
                if cached:
                    timestamp = cached.get("timestamp", 0)
                    data = cached.get("data")
                    if data is not None:
                        ttl = dynamic_ttl(data)
                        if time.time() - timestamp < ttl:
                            data = [
                                m for m in data
                                if not (espn_data._is_placeholder(m.get("home_team", ""))
                                        or espn_data._is_placeholder(m.get("away_team", "")))
                            ]
                            # Elo reload is cheap here thanks to the debounce guard.
                            math_engine.reload_elo_data()
                            archive = load_archive_from_db(archive_collection)
                            return _sync_archive_tips(
                                _enrich_edge(data, math_engine, odds_engine),
                                archive, archive_collection
                            )
            except Exception:
                pass

        # ── Slow path: cache miss or force refresh ──
        archive = load_archive_from_db(archive_collection)
        math_engine.reload_elo_data(archive=archive, force=True)

        # Fixture skeleton comes from ESPN (only source with played + upcoming).
        try:
            fixtures = espn_data.get_scoreboard()
        except Exception as e:
            try:
                cached = cache_collection.find_one({"_id": "matches_cache"})
                if cached and cached.get("data"):
                    print(f"ESPN unavailable, serving stale cache: {e}")
                    return _sync_archive_tips(
                        _enrich_edge(cached["data"], math_engine, odds_engine),
                        archive, archive_collection
                    )
            except Exception:
                pass
            raise HTTPException(status_code=503, detail=f"Fixture source unavailable: {e}")

        # Multi-bookmaker odds for upcoming games from The Odds API (best-effort).
        odds_lookup = _build_odds_api_lookup(odds_engine)
        id_index = build_archive_id_index(archive)

        results = []
        _bot_inputs = {}
        for fx in fixtures:
            home_raw = fx["home_team"]
            away_raw = fx["away_team"]
            date = fx.get("commence_time", "")

            # Keep the same _id the archive already uses for this pairing.
            match_id = resolve_archive_id(id_index, home_raw, away_raw, date) or fx["id"]

            # Prefer Odds-API multi-book bookmakers; fall back to ESPN/DraftKings.
            bookmakers = _match_odds_api(odds_lookup, home_raw, away_raw, date)
            if not bookmakers and fx.get("espn_odds"):
                bookmakers = _synth_bookmakers(fx["espn_odds"], home_raw, away_raw)

            raw_match = {
                "id": match_id,
                "home_team": home_raw,
                "away_team": away_raw,
                "commence_time": date,
                "round": fx.get("round", ""),
                "bookmakers": bookmakers or [],
            }
            is_ko_detected = _is_ko_round(fx.get("round", ""))

            odds = {}
            top_tip, max_xp = "N/A", 0.0
            elo_home_share = market_home_share = edge_home = None
            try:
                odds = extract_odds(raw_match)
            except ValueError:
                odds = {}

            # Completed games: show the frozen odds + algo tip from the archive
            # (recomputing with today's Elo would corrupt a past prediction).
            arc = archive.get(match_id) or {}
            arc_tip = (arc.get("prediction") or {}).get("top_tip")
            if fx.get("completed") and arc_tip:
                snap_odds = (arc.get("pre_match_snapshot") or {}).get("odds") or {}
                if all(k in snap_odds for k in ("home", "draw", "away")):
                    odds = snap_odds
                top_tip = arc_tip
                max_xp = float((arc.get("prediction") or {}).get("max_xp") or 0.0)
            elif odds:
                try:
                    math_engine.ensure_teams_exist(
                        TEAM_MAPPING.get(home_raw, home_raw),
                        TEAM_MAPPING.get(away_raw, away_raw),
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

                    is_ko = is_ko_detected
                    xg_h, xg_a = math_engine.derive_xg_from_odds(
                        prob_home, prob_draw, prob_away, prob_over25
                    )

                    if is_ko:
                        base_matrix = math_engine.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
                        p_draw_90 = float(np.sum(np.diag(base_matrix.values)))
                        et_factor = 1 + p_draw_90 / 3
                        xg_h *= et_factor
                        xg_a *= et_factor

                    sm = math_engine.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
                    df_xp = math_engine.calculate_expected_points(sm, is_ko_phase=is_ko)

                    if not df_xp.empty:
                        top_tip = df_xp.iloc[0]["Tipp"]
                        max_xp = float(df_xp.iloc[0]["xP"])

                    market_home_share = (true_probs["home"] / win_loss_pool) if win_loss_pool > 0 else 0.5
                    edge_home = elo_home_share - market_home_share

                    if top_tip != "N/A":
                        _bot_inputs[match_id] = {
                            "score_matrix": sm,
                            "base_xp_df": df_xp,
                            "true_probs": true_probs,
                            "prob_over25": prob_over25,
                        }
                except Exception:
                    top_tip, max_xp = "N/A", 0.0
                    elo_home_share = market_home_share = edge_home = None

            results.append({
                "id": match_id,
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
                "is_ko_phase": is_ko_detected,
                "actual_score": fx.get("actual_score"),
                "completed": fx.get("completed", False),
                "raw_match": raw_match,
            })

        # Cache update — merge with existing
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
                    # Never overwrite previously-captured odds with an odds-less
                    # fixture (e.g. a completed game whose odds ESPN no longer lists).
                    if old_o and not new_o:
                        merged_entry = dict(r)
                        merged_entry["odds"] = old_o
                        merged_entry["top_tip"] = prev.get("top_tip", "N/A")
                        merged_entry["max_xp"] = prev.get("max_xp", 0)
                        merged_entry["raw_match"] = prev.get("raw_match", r["raw_match"])
                        existing_matches[r["id"]] = merged_entry
                        continue
                    odds_changed = any(
                        abs(new_o.get(k, 0) - old_o.get(k, 0)) > 0.02
                        for k in ["home", "draw", "away"]
                    )
                    missing_edge = "edge_home" not in prev and r.get("edge_home") is not None
                    if not odds_changed and not missing_edge:
                        # Preserve fresh ESPN-sourced fields (result + recomputed KO flag).
                        prev.update({
                            "actual_score": r.get("actual_score"),
                            "completed": r.get("completed", False),
                            "is_ko_phase": r.get("is_ko_phase", False),
                        })
                        prev.setdefault("raw_match", {})["round"] = r["raw_match"].get("round", "")
                        existing_matches[r["id"]] = prev
                        continue
                existing_matches[r["id"]] = r
            # Drop stale placeholder bracket slots (teams undecided) that a
            # previous cache may still hold — the merge otherwise keeps them.
            merged = sorted(
                (m for m in existing_matches.values()
                 if not (espn_data._is_placeholder(m.get("home_team", ""))
                         or espn_data._is_placeholder(m.get("away_team", "")))),
                key=lambda m: m.get("raw_match", {}).get("commence_time", ""),
            )
            cache_collection.update_one(
                {"_id": "matches_cache"},
                {"$set": {"timestamp": time.time(), "data": merged}},
                upsert=True
            )
        except Exception as e:
            print(f"Fehler beim Speichern des Caches: {e}")

        # Archive: log pre-match snapshots + backfill bots
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
                            is_ko_phase=r.get("is_ko_phase", False)
                        )
                    except Exception as e:
                        print(f"Bot tips failed for {r['id']}: {e}")

                if r["id"] not in archive:
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
                            "is_ko_phase": r.get("is_ko_phase", False),
                            "round": r.get("raw_match", {}).get("round", ""),
                            "commence_time": r.get("raw_match", {}).get("commence_time"),
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
            print(f"Archive logging failed: {e}")

        for r in results:
            arc = archive.get(r["id"], {})
            r["bots"] = arc.get("prediction", {}).get("bots", {})

        return _sync_archive_tips(results, archive, archive_collection)

    return router
