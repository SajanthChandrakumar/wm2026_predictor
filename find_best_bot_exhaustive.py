"""
ULTRA-FINE exhaustive grid search: all 4 params at 0.1 step size.

  market_weight : 0.0 .. 1.0  (step 0.1)  => 11 values
  risk          : -1.0 .. 1.0 (step 0.1)  => 21 values
  draw_bias     : 0.0 .. 6.0  (step 0.1)  => 61 values
  underdog_bias : 0.0 .. 6.0  (step 0.1)  => 61 values

Total: 11 * 21 * 61 * 61 = 885,731 combinations
"""
import json
import time
import numpy as np
from src.math_engine import MathEngine

def run():
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

    market_weights  = [round(x * 0.1, 1) for x in range(11)]        # 11
    risks           = [round(x * 0.1 - 1.0, 1) for x in range(21)]  # 21
    draw_biases     = [round(x * 0.1, 1) for x in range(61)]        # 61
    underdog_biases = [round(x * 0.1, 1) for x in range(61)]        # 61

    total_combos = len(market_weights) * len(risks) * len(draw_biases) * len(underdog_biases)
    print(f"Grid: {len(market_weights)} x {len(risks)} x {len(draw_biases)} x {len(underdog_biases)} = {total_combos:,} combinations")

    tips = [(h, a) for h in range(6) for a in range(6)]
    is_draw_arr = np.array([1.0 if h == a else 0.0 for h, a in tips])
    db_arr = np.array(draw_biases)
    ub_arr = np.array(underdog_biases)

    best_score = -1
    best_params = {}
    top20 = []
    t0 = time.time()

    for mw_idx, mw in enumerate(market_weights):
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
                    for underdog_a, ev_a, std_a, act_pts in precomputed:
                        score = ev_a + r * std_a + db * is_draw_arr + ub * underdog_a
                        total_pts += act_pts[int(np.argmax(score))]

                    if total_pts > best_score:
                        best_score = total_pts
                        best_params = {"market_weight": mw, "risk": r, "draw_bias": db, "underdog_bias": ub}

                    top20.append((total_pts, {"market_weight": mw, "risk": r, "draw_bias": db, "underdog_bias": ub}))

        elapsed = time.time() - t0
        print(f"  mw={mw:.1f} done ({mw_idx+1}/{len(market_weights)}) - {elapsed:.1f}s elapsed - current best: {best_score}")

    print(f"\nTested {total_combos:,} combinations in {time.time()-t0:.1f}s.")

    top20.sort(key=lambda x: -x[0])
    top20 = top20[:20]

    print(f"\n{'='*60}")
    print(f"BEST SCORE: {best_score}")
    print(f"BEST PARAMS: {best_params}")
    print(f"{'='*60}")

    print("\nTop 20:")
    for i, (pts, p) in enumerate(top20, 1):
        print(f"  {i:2d}. {pts:4.0f} pts  mw={p['market_weight']:.1f}  risk={p['risk']:.1f}  draw={p['draw_bias']:.1f}  underdog={p['underdog_bias']:.1f}")

if __name__ == "__main__":
    run()
