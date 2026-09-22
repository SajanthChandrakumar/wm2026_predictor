import json
import numpy as np
from src.math_engine import MathEngine

def run_grid_search():
    with open("data/live_archive_filled.json", "r", encoding="utf-8") as f:
        archive = json.load(f)

    engine = MathEngine("data/elo_ratings.csv")

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

        meta = match.get("metadata", {})
        is_ko = meta.get("is_ko_phase", False)
        elo_state = snap.get("elo_state") or {}
        elo_home = elo_state.get("home_rating", 1500.0)
        elo_away = elo_state.get("away_rating", 1500.0)

        completed.append((mid, odds, elo_home, elo_away, actual, is_ko))

    print(f"Loaded {len(completed)} completed matches.")

    market_weights = [0.0, 0.3, 0.5, 0.7, 0.85, 1.0]
    risks = [-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0]
    draw_biases = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]
    underdog_biases = [0.0, 0.5, 1.0, 1.5, 2.0]

    tips = [(t_home, t_away) for t_home in range(6) for t_away in range(6)]
    is_draw_arr = np.array([1.0 if t_home == t_away else 0.0 for t_home, t_away in tips])

    all_results = []

    # For each (mw, match) precompute per-tip: ev, std, is_underdog_win, and the
    # actual points that tip would have scored. risk/draw_bias/underdog_bias never
    # change the score_matrix, so this is the only place scipy's xG fit runs.
    for mw in market_weights:
        precomputed = []
        for mid, odds, elo_home, elo_away, actual, is_ko in completed:
            sm, true_probs = engine.custom_bot_score_matrix(odds, elo_home, elo_away, mw, is_ko)
            home_is_underdog = true_probs["home"] < true_probs["away"]

            mat = sm.values
            rows = [int(x) for x in sm.index]
            cols = [int(x) for x in sm.columns]

            ev_list, std_list, underdog_list = [], [], []
            for t_home, t_away in tips:
                pts_grid = np.array([[engine._tip_points(t_home, t_away, ah, aw, is_ko) for aw in cols] for ah in rows])
                ev = float(np.sum(pts_grid * mat))
                ev_sq = float(np.sum((pts_grid ** 2) * mat))
                std = (max(0.0, ev_sq - ev ** 2)) ** 0.5
                underdog_wins = (t_home > t_away) if home_is_underdog else (t_away > t_home)
                ev_list.append(ev)
                std_list.append(std)
                underdog_list.append(1.0 if underdog_wins else 0.0)

            try:
                a_home, a_away = map(int, actual.split(":"))
                actual_pts = np.array([engine._tip_points(t_home, t_away, a_home, a_away, is_ko) for t_home, t_away in tips])
            except Exception:
                actual_pts = np.zeros(len(tips))

            precomputed.append((np.array(underdog_list), np.array(ev_list), np.array(std_list), actual_pts))

        for r in risks:
            for db in draw_biases:
                for ub in underdog_biases:
                    total_pts = 0
                    for underdog_arr, ev_arr, std_arr, actual_pts in precomputed:
                        score = ev_arr + r * std_arr + db * is_draw_arr + ub * underdog_arr
                        best_idx = int(np.argmax(score))
                        total_pts += actual_pts[best_idx]

                    params = {"market_weight": mw, "risk": r, "draw_bias": db, "underdog_bias": ub}
                    all_results.append((total_pts, params))

    print(f"\nTested {len(all_results)} combinations locally.")
    all_results.sort(key=lambda x: -x[0])
    best_score, best_params = all_results[0]
    print(f"Best Score: {best_score}")
    print(f"Best Params: {best_params}")

    print("\nTop 10:")
    for pts, params in all_results[:10]:
        print(f"  {pts}  {params}")

if __name__ == "__main__":
    run_grid_search()
