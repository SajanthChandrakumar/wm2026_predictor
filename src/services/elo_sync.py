import os
import json
import time
import logging

from src.math_engine import MathEngine
from src.services.archive import load_archive_from_db, upsert_archive_entry

logger = logging.getLogger(__name__)

SCORES_CACHE_TTL = 1800


def perform_elo_sync(
    math_engine: MathEngine,
    odds_engine_cls,
    archive_collection,
    scores_cache_path: str,
    display_mapping: dict,
) -> dict:
    logger.info("Elo sync triggered...")
    odds_engine = odds_engine_cls()
    processed_json_path = os.path.join(
        os.path.dirname(math_engine.elo_csv_path), 'processed_matches.json'
    )

    scores_cache = {}
    if os.path.exists(scores_cache_path):
        try:
            with open(scores_cache_path, 'r', encoding='utf-8') as f:
                scores_cache = json.load(f)
        except Exception:
            pass

    if time.time() - scores_cache.get("timestamp", 0) < SCORES_CACHE_TTL:
        completed_matches = scores_cache.get("data", [])
        logger.info("Elo sync: using cached scores (< 30 min old)")
    else:
        completed_matches = odds_engine.get_completed_scores(days_from=3)
        try:
            os.makedirs(os.path.dirname(scores_cache_path), exist_ok=True)
            with open(scores_cache_path, 'w', encoding='utf-8') as f:
                json.dump({"timestamp": time.time(), "data": completed_matches}, f, indent=4)
        except Exception as e:
            logger.warning(f"Scores cache write failed: {e}")

    updates = math_engine.update_elo_from_api_scores(
        api_scores=completed_matches,
        processed_matches_file=processed_json_path
    )
    if updates > 0:
        math_engine.elo_df.to_csv(math_engine.elo_csv_path, index=False)
        logger.info(f"Elo sync completed: {updates} updates.")

    _grade_archive(
        math_engine, completed_matches, archive_collection, display_mapping
    )

    if updates > 0:
        return {"status": "success", "updates": updates}
    else:
        logger.info("Elo sync completed: No new matches.")
        return {"status": "info", "message": "No new matches."}


def _grade_archive(
    math_engine: MathEngine,
    completed_matches: list,
    archive_collection,
    display_mapping: dict,
) -> None:
    """Post-match grading + retroactive entry creation + algo-tip reconstruction."""
    try:
        archive = load_archive_from_db(archive_collection)
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
                new_entry = {
                    "metadata": {
                        "home_team": home_team,
                        "away_team": away_team,
                        "home_disp": display_mapping.get(home_team, home_team),
                        "away_disp": display_mapping.get(away_team, away_team),
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

            algo_tip = archive[match_id]["prediction"].get("top_tip")
            user_tip = archive[match_id]["prediction"].get("user_tip")
            is_ko = archive[match_id]["metadata"]["is_ko_phase"]
            active_tip = user_tip if user_tip else algo_tip
            archive[match_id]["post_match_result"]["status"] = "completed"
            archive[match_id]["post_match_result"]["actual_score"] = actual_score_str
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

        # Reconstruction: algo tips for completed entries without pre_match_snapshot
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
            upsert_archive_entry(archive_collection, mid, entry)

        if graded:
            logger.info(f"Archive grading completed: {graded} predictions scored.")
        if retro:
            logger.info(f"Retroactive archive entries created: {retro} matches.")
        if reconstructed:
            logger.info(f"Algo tips reconstructed: {reconstructed} matches (Elo-only pipeline).")
    except Exception as e:
        logger.error(f"Archive grading failed: {e}")
