"""
Three "learning" bots whose tips/parameters are derived from the historical
archive instead of being fixed:

  Optimizer — Grid-search over the 4 Build-a-Bot knobs; picks the combination
              that would have maximised total points across all completed
              matches with a pre-match snapshot.
  Momentum  — Same grid-search, but match contributions are exponentially
              weighted toward recent games (decay 0.9 per match).
  Mitläufer — Follow-the-leader: per completed match, copies the tip of the
              house-bot that has accumulated the most points so far. Pure
              online-learning, no grid.

Result is a list of bot dicts with the same shape the frontend already expects
(name, pts, tipped, tendency, pointsByMatch) plus a `learned_label` describing
what the bot currently "knows".
"""
from __future__ import annotations

import numpy as np

from src.math_engine import MathEngine


# ── Grid for Optimizer / Momentum ─────────────────────────────────────────
MARKET_WEIGHTS = (0.0, 0.25, 0.5, 0.7, 1.0)
RISKS          = (-0.5, 0.0, 0.5)
DRAW_BIASES    = (0.0, 2.0, 4.0)
UNDERDOG_BIASES = (0.0, 2.0, 4.0)

MOMENTUM_DECAY = 0.9

HOUSE_BOTS = ("broker", "professor", "sniper", "gambler")
HOUSE_BOT_DISPLAY = {
    "broker": "Broker", "professor": "Professor",
    "sniper": "X-Sniper", "gambler": "Zocker",
}


def _completed_with_snapshot(archive: dict) -> list[tuple]:
    """Same filter the Build-a-Bot simulation uses, chronologically sorted."""
    items = []
    for mid, match in archive.items():
        pmr = match.get("post_match_result") or {}
        if pmr.get("status") != "completed":
            continue
        actual = pmr.get("actual_score")
        snap = match.get("pre_match_snapshot") or {}
        odds = snap.get("odds") or {}
        if not actual or not all(k in odds for k in ("home", "draw", "away")):
            continue
        items.append((mid, match, snap, odds, actual))
    items.sort(key=lambda x: x[2].get("timestamp_recorded") or "")
    return items


_TIP_LABELS = [f"{h}:{a}" for h in range(6) for a in range(6)]
_TIP_HOME   = np.array([h for h in range(6) for _ in range(6)], dtype=int)
_TIP_AWAY   = np.array([a for _ in range(6) for a in range(6)], dtype=int)
_IS_DRAW    = (_TIP_HOME == _TIP_AWAY)


def _tip_stats_for_match(math_engine: MathEngine, sm, true_probs, is_ko: bool, actual: str):
    """
    Precompute, for one (match, market_weight) cell, three 36-vectors:
      ev[i]     — expected points if you tip tip i
      std[i]    — std-dev of points for tip i
      pts[i]    — actual points the tip would have scored against `actual`
    Plus a single bool: home_is_underdog. The grid loop then only does vector math.
    """
    ev_arr  = np.zeros(36)
    std_arr = np.zeros(36)
    pts_arr = np.zeros(36)
    try:
        a_h, a_a = map(int, actual.split(":"))
    except Exception:
        a_h = a_a = -1
    for i in range(36):
        t_h, t_a = int(_TIP_HOME[i]), int(_TIP_AWAY[i])
        ev, std = math_engine._points_distribution(t_h, t_a, sm, is_ko)
        ev_arr[i] = ev
        std_arr[i] = std
        if a_h >= 0:
            pts_arr[i] = MathEngine._tip_points(t_h, t_a, a_h, a_a, is_ko)
    home_is_underdog = true_probs["home"] < true_probs["away"]
    return ev_arr, std_arr, pts_arr, home_is_underdog


def _build_stats_cache(math_engine: MathEngine, completed: list) -> dict:
    """Per-(match, market_weight) (ev[36], std[36], pts[36], underdog_wins[36])."""
    stats_cache = {}
    for i, (mid, match, snap, odds, actual) in enumerate(completed):
        meta = match.get("metadata", {})
        is_ko = meta.get("is_ko_phase", False)
        elo_state = snap.get("elo_state") or {}
        elo_h = elo_state.get("home_rating", 1500.0)
        elo_a = elo_state.get("away_rating", 1500.0)
        for mw in MARKET_WEIGHTS:
            try:
                sm, tp = math_engine.custom_bot_score_matrix(odds, elo_h, elo_a, mw, is_ko)
                ev, std, pts, home_is_under = _tip_stats_for_match(
                    math_engine, sm, tp, is_ko, actual
                )
                underdog_wins = (_TIP_HOME > _TIP_AWAY) if home_is_under else (_TIP_AWAY > _TIP_HOME)
                stats_cache[(i, mw)] = (ev, std, pts, underdog_wins)
            except Exception:
                stats_cache[(i, mw)] = None
    return stats_cache


def _grid_search(completed: list, stats_cache: dict, weights: list[float]) -> dict:
    """
    Pure-NumPy grid search over the precomputed stat tables.
    `weights[i]` is the recency weight for match i.
    """
    n = len(completed)
    w = np.asarray(weights, dtype=float)
    best_params = None
    best_score = float("-inf")
    for mw in MARKET_WEIGHTS:
        for risk in RISKS:
            for db in DRAW_BIASES:
                for ub in UNDERDOG_BIASES:
                    total = 0.0
                    for i in range(n):
                        cached = stats_cache.get((i, mw))
                        if cached is None:
                            continue
                        ev, std, pts, underdog_wins = cached
                        score = ev + risk * std + db * _IS_DRAW + ub * underdog_wins
                        idx = int(np.argmax(score))
                        total += pts[idx] * w[i]
                    if total > best_score:
                        best_score = total
                        best_params = {
                            "market_weight": mw, "risk": risk,
                            "draw_bias": db, "underdog_bias": ub,
                        }
    return best_params or {
        "market_weight": 0.7, "risk": 0.0, "draw_bias": 0.0, "underdog_bias": 0.0,
    }


def _replay_from_cache(completed: list, stats_cache: dict, params: dict) -> dict:
    """Replay using cached stat tables — no scipy fits, instant."""
    mw = params["market_weight"]
    risk = params["risk"]
    db = params["draw_bias"]
    ub = params["underdog_bias"]
    pts_total = 0
    correct = 0
    points_by_match = {}
    tipped = 0
    for i, (mid, *_rest) in enumerate(completed):
        cached = stats_cache.get((i, mw))
        if cached is None:
            points_by_match[mid] = 0
            continue
        ev, std, pts, underdog_wins = cached
        score = ev + risk * std + db * _IS_DRAW + ub * underdog_wins
        idx = int(np.argmax(score))
        p = int(pts[idx])
        pts_total += p
        tipped += 1
        if p >= 5:
            correct += 1
        points_by_match[mid] = p
    return {
        "pts": pts_total,
        "tipped": tipped,
        "tendency": correct,
        "pointsByMatch": points_by_match,
    }


def _format_params_label(p: dict) -> str:
    mw = int(round(p["market_weight"] * 100))
    risk = p["risk"]
    risk_str = "+0" if risk == 0 else f"{risk:+.1f}"
    parts = [f"Markt {mw}% · Risiko {risk_str}"]
    extras = []
    if p["draw_bias"] > 0:
        extras.append(f"Draw +{int(p['draw_bias'])}")
    if p["underdog_bias"] > 0:
        extras.append(f"Underdog +{int(p['underdog_bias'])}")
    if extras:
        parts.append(" · ".join(extras))
    return " · ".join(parts)


def _follow_the_leader(archive: dict) -> dict:
    """
    Chronological pass: for each match where bot_points exist, copy the tip of
    the house-bot currently leading on cumulative points. First match falls back
    to 'broker' (gleichstand). Counts only matches where the chosen leader
    actually had a tip stored.
    """
    completed = []
    for mid, m in archive.items():
        pmr = m.get("post_match_result") or {}
        if pmr.get("status") != "completed" or not pmr.get("actual_score"):
            continue
        if not (pmr.get("bot_points") or m.get("prediction", {}).get("bots")):
            continue
        completed.append((mid, m))
    completed.sort(key=lambda x: (x[1].get("pre_match_snapshot") or {}).get("timestamp_recorded") or "")

    cumulative = {b: 0 for b in HOUSE_BOTS}
    pts_total = 0
    tipped = 0
    correct = 0
    points_by_match = {}
    last_leader = "broker"
    leader_counts = {b: 0 for b in HOUSE_BOTS}

    for mid, match in completed:
        # Leader = argmax over cumulative; ties → keep last_leader for stability.
        if any(v > 0 for v in cumulative.values()):
            top = max(cumulative.items(), key=lambda kv: kv[1])
            if top[1] > 0:
                # break ties in favour of last_leader
                if cumulative.get(last_leader, -1) < top[1]:
                    last_leader = top[0]
        leader = last_leader
        leader_counts[leader] = leader_counts.get(leader, 0) + 1

        bots = match.get("prediction", {}).get("bots", {}) or {}
        tip = (bots.get(leader) or {}).get("tip")
        actual = match["post_match_result"]["actual_score"]
        is_ko = (match.get("metadata") or {}).get("is_ko_phase", False)

        if tip:
            pts = MathEngine.calculate_actual_points(tip, actual, is_ko)
            pts_total += pts
            tipped += 1
            if pts >= 5:
                correct += 1
            points_by_match[mid] = pts
        else:
            points_by_match[mid] = 0

        # Update cumulative AFTER picking (leader must be based on pre-match state).
        bp = match.get("post_match_result", {}).get("bot_points") or {}
        for b in HOUSE_BOTS:
            if bp.get(b) is not None:
                cumulative[b] += bp[b]

    # Final leader for label
    if any(v > 0 for v in leader_counts.values()):
        most_followed = max(leader_counts.items(), key=lambda kv: kv[1])[0]
        label = f"Folgt: {HOUSE_BOT_DISPLAY.get(most_followed, most_followed)}"
    else:
        label = "Noch keine Historie"

    return {
        "pts": pts_total,
        "tipped": tipped,
        "tendency": correct,
        "pointsByMatch": points_by_match,
        "learned_label": label,
    }


def compute_learning_bots(math_engine: MathEngine, archive: dict) -> list[dict]:
    """Build the 3 learning-bot result dicts the frontend renders."""
    completed = _completed_with_snapshot(archive)
    n = len(completed)

    out = []

    if n >= 2:
        # Build the stat cache once; both grid-searches reuse it.
        stats_cache = _build_stats_cache(math_engine, completed)

        # Optimizer: equal weights
        eq_weights = [1.0] * n
        opt_params = _grid_search(completed, stats_cache, eq_weights)
        opt_stats = _replay_from_cache(completed, stats_cache, opt_params)
        out.append({
            "key": "optimizer",
            "name": "Optimizer",
            "color": "#2dd4bf",
            "learned_label": _format_params_label(opt_params),
            "params": opt_params,
            **opt_stats,
        })

        # Momentum: exponentially recency-weighted
        # weights[i] = decay^(n - 1 - i); newest match has weight 1.0
        mom_weights = [MOMENTUM_DECAY ** (n - 1 - i) for i in range(n)]
        mom_params = _grid_search(completed, stats_cache, mom_weights)
        mom_stats = _replay_from_cache(completed, stats_cache, mom_params)
        out.append({
            "key": "momentum",
            "name": "Momentum",
            "color": "#e879f9",
            "learned_label": _format_params_label(mom_params),
            "params": mom_params,
            **mom_stats,
        })

    # Mitläufer: needs at least 2 archive matches with bot_points
    follower = _follow_the_leader(archive)
    if follower["tipped"] > 0:
        out.append({
            "key": "follower",
            "name": "Mitläufer",
            "color": "#a3e635",
            **follower,
        })

    return out
