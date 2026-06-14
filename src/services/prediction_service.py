import pandas as pd
import numpy as np

def compute_bot_tips(
    score_matrix: pd.DataFrame,
    base_xp_df: pd.DataFrame,
    true_probs: dict,
    prob_over25: float | None,
    home_team: str,
    away_team: str,
    match_id: str,
    is_ko_phase: bool = False,
    math_core=None,
    elo_service=None
) -> dict:
    """
    Computes tips for all bots.
    math_core is the src.core.math module.
    elo_service is the elo service to fetch Elo probabilities.
    """
    bots = {}
    fallback_tip = base_xp_df.iloc[0]["Tipp"] if not base_xp_df.empty else "1:0"

    # 1. The Broker (100% Odds)
    try:
        xg_h_o, xg_a_o = math_core.derive_xg_from_odds(true_probs["home"], true_probs["draw"], true_probs["away"], prob_over25)
        sm_o = math_core.generate_exact_score_matrix(xg_h_o, xg_a_o, max_goals=10)
        xp_o = math_core.calculate_expected_points(sm_o, is_ko_phase)
        bots["broker"] = {"tip": xp_o.iloc[0]["Tipp"] if not xp_o.empty else fallback_tip}
    except: bots["broker"] = {"tip": fallback_tip}

    # 2. The Professor (100% Elo + Market Totals)
    try:
        p_h_e, p_a_e = elo_service.get_match_elo_probabilities(home_team, away_team)
        p_d_e = max(0.15, 1.0 - p_h_e - p_a_e)
        total_e = p_h_e + p_a_e + p_d_e
        xg_h_e, xg_a_e = math_core.derive_xg_from_odds(p_h_e / total_e, p_d_e / total_e, p_a_e / total_e, prob_over25)
        sm_e = math_core.generate_exact_score_matrix(xg_h_e, xg_a_e, max_goals=10)
        xp_e = math_core.calculate_expected_points(sm_e, is_ko_phase)
        bots["professor"] = {"tip": xp_e.iloc[0]["Tipp"] if not xp_e.empty else fallback_tip}
    except: bots["professor"] = {"tip": fallback_tip}

    # 3. The Rebel (Der Underdog)
    try:
        full_xp_df = math_core.calculate_expected_points(score_matrix, is_ko_phase, top_n=36)
        if true_probs["home"] > true_probs["away"]:
            rebel_df = full_xp_df[full_xp_df["Tipp"].apply(lambda x: int(x.split(":")[0]) < int(x.split(":")[1]))]
        else:
            rebel_df = full_xp_df[full_xp_df["Tipp"].apply(lambda x: int(x.split(":")[0]) > int(x.split(":")[1]))]
            
        if not rebel_df.empty:
            bots["rebel"] = {"tip": rebel_df.iloc[0]["Tipp"]}
        else:
            bots["rebel"] = {"tip": fallback_tip}
    except: bots["rebel"] = {"tip": fallback_tip}

    # 4. The X-Sniper (Always highest xP draw)
    try:
        draw_tip = None
        if not base_xp_df.empty:
            draws = base_xp_df[base_xp_df["Tipp"].apply(lambda x: x.split(":")[0] == x.split(":")[1])]
            if not draws.empty:
                draw_tip = draws.iloc[0]["Tipp"]
        bots["sniper"] = {"tip": draw_tip if draw_tip else "1:1"}
    except: bots["sniper"] = {"tip": "1:1"}

    # 5. Der Zocker (The Gambler) - High Variance / High Upside
    try:
        if not base_xp_df.empty:
            top_10 = math_core.calculate_expected_points(score_matrix, is_ko_phase, top_n=10)
            if not top_10.empty:
                weights = []
                for _, row in top_10.iterrows():
                    th, ta = map(int, row["Tipp"].split(":"))
                    total_goals = th + ta
                    var_weight = 1.0 + (total_goals * 0.2)
                    weights.append(var_weight)
                weights = np.array(weights)
                weights /= weights.sum()
                rng = np.random.default_rng(seed=hash(match_id) % (2**32))
                bots["gambler"] = {"tip": top_10.iloc[rng.choice(len(top_10), p=weights)]["Tipp"]}
            else: bots["gambler"] = {"tip": fallback_tip}
        else: bots["gambler"] = {"tip": fallback_tip}
    except: bots["gambler"] = {"tip": fallback_tip}

    return bots
