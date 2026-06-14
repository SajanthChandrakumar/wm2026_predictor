import numpy as np
import pandas as pd
from scipy import stats, optimize

def remove_margin(odds_home: float, odds_draw: float, odds_away: float) -> dict[str, float]:
    implied_h = 1.0 / odds_home
    implied_d = 1.0 / odds_draw
    implied_a = 1.0 / odds_away
    margin = implied_h + implied_d + implied_a
    return {
        "home": implied_h / margin,
        "draw": implied_d / margin,
        "away": implied_a / margin,
    }

def get_elo_probability(rating_a: float, rating_b: float, is_a_host: bool = False, is_b_host: bool = False) -> float:
    dr = rating_a - rating_b
    if is_a_host: dr += 100
    if is_b_host: dr -= 100
    return 1 / (10 ** (-dr / 400) + 1)

def derive_xg_from_odds(prob_home: float, prob_draw: float, prob_away: float, prob_over25: float = None) -> tuple[float, float]:
    def cost_function(lambdas):
        l_home, l_away = lambdas
        max_goals = 10
        poisson_home = stats.poisson.pmf(np.arange(max_goals), l_home)
        poisson_away = stats.poisson.pmf(np.arange(max_goals), l_away)
        prob_matrix = np.outer(poisson_home, poisson_away)

        rho = -0.15
        prob_matrix[0, 0] *= 1 - (l_home * l_away * rho)
        prob_matrix[1, 0] *= 1 + (l_home * rho)
        prob_matrix[0, 1] *= 1 + (l_away * rho)
        prob_matrix[1, 1] *= 1 - rho
        prob_matrix = prob_matrix / np.sum(prob_matrix)

        calc_home = np.sum(np.tril(prob_matrix, -1))
        calc_draw = np.sum(np.diag(prob_matrix))
        calc_away = np.sum(np.triu(prob_matrix, 1))

        error = ((calc_home - prob_home) ** 2 + (calc_draw - prob_draw) ** 2 + (calc_away - prob_away) ** 2)

        if prob_over25 is not None:
            goals_h, goals_a = np.indices((max_goals, max_goals))
            calc_over25 = np.sum(prob_matrix[(goals_h + goals_a) > 2])
            error += (calc_over25 - prob_over25) ** 2

        return error

    bounds = ((0.1, 5.0), (0.1, 5.0))
    result = optimize.minimize(cost_function, x0=np.array([1.2, 1.2]), bounds=bounds, method='L-BFGS-B')
    return result.x[0], result.x[1]

def generate_exact_score_matrix(lambda_home: float, lambda_away: float, max_goals: int = 5, rho: float = -0.15) -> pd.DataFrame:
    poisson_home = stats.poisson.pmf(np.arange(max_goals + 1), lambda_home)
    poisson_away = stats.poisson.pmf(np.arange(max_goals + 1), lambda_away)
    prob_matrix = np.outer(poisson_home, poisson_away)

    prob_matrix[0, 0] *= 1 - (lambda_home * lambda_away * rho)
    prob_matrix[1, 0] *= 1 + (lambda_home * rho)
    prob_matrix[0, 1] *= 1 + (lambda_away * rho)
    prob_matrix[1, 1] *= 1 - rho
    prob_matrix = prob_matrix / np.sum(prob_matrix)

    df = pd.DataFrame(prob_matrix)
    df.index.name = "Home Goals"
    df.columns.name = "Away Goals"
    return df

def calculate_actual_points(tipped_score: str, actual_score: str, is_ko_phase: bool = False) -> int:
    try:
        t_h, t_a = map(int, tipped_score.split(":"))
        a_h, a_a = map(int, actual_score.split(":"))
    except ValueError:
        return 0
    return _tip_points(t_h, t_a, a_h, a_a, is_ko_phase)

def _tip_points(tipped_home: int, tipped_away: int, actual_home: int, actual_away: int, is_ko_phase: bool = False) -> int:
    if tipped_home == actual_home and tipped_away == actual_away:
        pts = 8
    elif (tipped_home - tipped_away) == (actual_home - actual_away) and tipped_home != tipped_away:
        pts = 6
    elif (tipped_home > tipped_away and actual_home > actual_away) or (tipped_home < tipped_away and actual_home < actual_away):
        pts = 5
    elif tipped_home == tipped_away and actual_home == actual_away:
        pts = 5
    else:
        pts = 0

    if is_ko_phase and pts > 0:
        pts += 2
    return pts

def _points_distribution(t_home: int, t_away: int, score_matrix: pd.DataFrame, is_ko_phase: bool) -> tuple[float, float]:
    ev = 0.0
    ev_sq = 0.0
    for a_home_str in score_matrix.index:
        for a_away_str in score_matrix.columns:
            prob = score_matrix.loc[a_home_str, a_away_str]
            if prob > 0:
                pts = _tip_points(t_home, t_away, int(a_home_str), int(a_away_str), is_ko_phase)
                ev += pts * prob
                ev_sq += (pts ** 2) * prob
    variance = max(0.0, ev_sq - ev ** 2)
    return ev, variance ** 0.5

def calculate_expected_points(score_matrix: pd.DataFrame, is_ko_phase: bool = False, top_n: int = 5) -> pd.DataFrame:
    results = []
    max_tip_goals = 5
    for t_home in range(max_tip_goals + 1):
        for t_away in range(max_tip_goals + 1):
            xp, _ = _points_distribution(t_home, t_away, score_matrix, is_ko_phase)
            results.append({"Tipp": f"{t_home}:{t_away}", "xP": xp})
    df_xp = pd.DataFrame(results)
    df_xp = df_xp.sort_values(by="xP", ascending=False).head(top_n).reset_index(drop=True)
    return df_xp

def calculate_new_elo(rating_a: float, rating_b: float, actual_result_a: float, k_factor: int = 60, is_a_host: bool = False, is_b_host: bool = False, goal_diff: int = 0) -> tuple[float, float]:
    expected_a = get_elo_probability(rating_a, rating_b, is_a_host=is_a_host, is_b_host=is_b_host)
    expected_b = 1 - expected_a
    gd = abs(goal_diff)
    if gd <= 1:
        mov_multiplier = 1.0
    elif gd == 2:
        mov_multiplier = 1.5
    else:
        mov_multiplier = 1.75 + (gd - 3) / 8
    k = k_factor * mov_multiplier
    new_rating_a = rating_a + k * (actual_result_a - expected_a)
    new_rating_b = rating_b + k * ((1 - actual_result_a) - expected_b)
    return new_rating_a, new_rating_b
