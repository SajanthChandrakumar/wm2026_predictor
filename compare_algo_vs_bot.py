"""
Compare xP-Optimiser (algo) vs Best Build-a-Bot match by match.
Break down by phase (group vs KO), show where the differences are.
"""
import json
from src.math_engine import MathEngine

with open("data/live_archive_filled.json", "r", encoding="utf-8") as f:
    archive = json.load(f)

engine = MathEngine("data/elo_ratings.csv")
best_params = {"market_weight": 0.2, "risk": 1.0, "draw_bias": 0.5, "underdog_bias": 1.2}

# Collect per-match data
rows = []
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

    algo_pts = pmr.get("algo_points", 0)
    algo_tip = match.get("prediction", {}).get("top_tip", "?")

    try:
        bot_tip = engine.compute_custom_bot_tip(odds, elo_home, elo_away, best_params, is_ko)
        bot_pts = engine.calculate_actual_points(bot_tip, actual, is_ko)
    except:
        bot_tip = "?"
        bot_pts = 0

    home = meta.get("home_team", "?")
    away = meta.get("away_team", "?")
    rows.append({
        "home": home, "away": away, "actual": actual, "is_ko": is_ko,
        "algo_tip": algo_tip, "algo_pts": algo_pts,
        "bot_tip": bot_tip, "bot_pts": bot_pts,
        "diff": bot_pts - algo_pts
    })

# Sort by commence_time via archive order
print(f"{'='*80}")
print(f"ALGO vs BEST BOT – Match-by-Match Comparison ({len(rows)} matches)")
print(f"{'='*80}")

# Phase breakdown
group = [r for r in rows if not r["is_ko"]]
ko = [r for r in rows if r["is_ko"]]

algo_group = sum(r["algo_pts"] for r in group)
bot_group = sum(r["bot_pts"] for r in group)
algo_ko = sum(r["algo_pts"] for r in ko)
bot_ko = sum(r["bot_pts"] for r in ko)

print(f"\n--- PHASE BREAKDOWN ---")
print(f"{'Phase':<15} {'Spiele':>6} {'Algo':>8} {'Bot':>8} {'Diff':>8} {'Algo/Sp':>8} {'Bot/Sp':>8}")
print(f"{'Gruppenphase':<15} {len(group):>6} {algo_group:>8} {bot_group:>8} {bot_group-algo_group:>+8} {algo_group/max(len(group),1):>8.2f} {bot_group/max(len(group),1):>8.2f}")
print(f"{'KO-Phase':<15} {len(ko):>6} {algo_ko:>8} {bot_ko:>8} {bot_ko-algo_ko:>+8} {algo_ko/max(len(ko),1):>8.2f} {bot_ko/max(len(ko),1):>8.2f}")
print(f"{'TOTAL':<15} {len(rows):>6} {algo_group+algo_ko:>8} {bot_group+bot_ko:>8} {(bot_group+bot_ko)-(algo_group+algo_ko):>+8}")

# Scoring type breakdown
algo_exact = sum(1 for r in rows if r["algo_tip"] == r["actual"])
bot_exact = sum(1 for r in rows if r["bot_tip"] == r["actual"])

algo_tendency = 0
bot_tendency = 0
algo_zero = 0
bot_zero = 0
same_tip = 0

for r in rows:
    if r["algo_tip"] == r["bot_tip"]:
        same_tip += 1
    # Check tendency (non-exact, non-zero)
    if r["algo_pts"] > 0 and r["algo_tip"] != r["actual"]:
        algo_tendency += 1
    if r["bot_pts"] > 0 and r["bot_tip"] != r["actual"]:
        bot_tendency += 1
    if r["algo_pts"] == 0:
        algo_zero += 1
    if r["bot_pts"] == 0:
        bot_zero += 1

print(f"\n--- TREFFERQUOTE ---")
print(f"{'Metrik':<30} {'Algo':>8} {'Bot':>8}")
print(f"{'Exakte Treffer':<30} {algo_exact:>8} {bot_exact:>8}")
print(f"{'Tendenz/Differenz richtig':<30} {algo_tendency:>8} {bot_tendency:>8}")
print(f"{'Komplett daneben (0 Pkt)':<30} {algo_zero:>8} {bot_zero:>8}")
print(f"{'Gleicher Tipp wie Algo':<30} {'':>8} {same_tip:>8}")

# Show biggest differences (bot > algo)
print(f"\n--- TOP 10: Bot BESSER als Algo ---")
bot_better = sorted([r for r in rows if r["diff"] > 0], key=lambda x: -x["diff"])
for r in bot_better[:10]:
    phase = "KO" if r["is_ko"] else "GR"
    mult = " (2x)" if r["is_ko"] else ""
    print(f"  [{phase}] {r['home']:15s} vs {r['away']:15s} | Actual: {r['actual']} | Algo: {r['algo_tip']}->{r['algo_pts']:2d} | Bot: {r['bot_tip']}->{r['bot_pts']:2d} | D={r['diff']:+d}{mult}")

print(f"\n--- TOP 10: Algo BESSER als Bot ---")
algo_better = sorted([r for r in rows if r["diff"] < 0], key=lambda x: x["diff"])
for r in algo_better[:10]:
    phase = "KO" if r["is_ko"] else "GR"
    mult = " (2x)" if r["is_ko"] else ""
    print(f"  [{phase}] {r['home']:15s} vs {r['away']:15s} | Actual: {r['actual']} | Algo: {r['algo_tip']}->{r['algo_pts']:2d} | Bot: {r['bot_tip']}->{r['bot_pts']:2d} | D={r['diff']:+d}{mult}")

# Summary stats
total_bot_advantage = sum(r["diff"] for r in rows if r["diff"] > 0)
total_algo_advantage = sum(-r["diff"] for r in rows if r["diff"] < 0)
print(f"\n--- SUMMARY ---")
print(f"Bot gewann Punkte in {len(bot_better)} Spielen (total +{total_bot_advantage})")
print(f"Algo gewann Punkte in {len(algo_better)} Spielen (total +{total_algo_advantage})")
print(f"Gleichstand in {len(rows) - len(bot_better) - len(algo_better)} Spielen")
print(f"Net difference: {total_bot_advantage - total_algo_advantage:+d} (= Bot {bot_group+bot_ko} - Algo {algo_group+algo_ko})")
