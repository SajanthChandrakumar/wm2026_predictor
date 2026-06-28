import logging

import numpy as np
from fastapi import APIRouter, Request, HTTPException

from src.constants import TEAM_MAPPING, TOTALS_CACHE_TTL
from src.services.odds_helpers import extract_odds, fetch_or_cache_totals
from src.math_engine import MathEngine

logger = logging.getLogger(__name__)


def init_router(math_engine, odds_engine, cache_collection, limiter):
    router = APIRouter(prefix="/api")

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
            match_data = fetch_or_cache_totals(event_id, match_data, odds_engine, cache_collection, TOTALS_CACHE_TTL)

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

    return router
