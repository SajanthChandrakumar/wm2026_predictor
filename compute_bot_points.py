import json

with open("data/live_archive_filled.json", "r", encoding="utf-8") as f:
    archive = json.load(f)

bot_totals = {}
algo_total = 0
user_total = 0
match_count = 0

for mid, match in archive.items():
    pmr = match.get("post_match_result", {})
    if pmr.get("status") != "completed":
        continue
    match_count += 1
    algo_total += pmr.get("algo_points", 0)
    user_total += pmr.get("points_earned", 0)
    for bot, pts in pmr.get("bot_points", {}).items():
        bot_totals[bot] = bot_totals.get(bot, 0) + pts

print(f"Matches: {match_count}")
print(f"\nUser (manual tips): {user_total}")
print(f"Algo (xP-Optimiser): {algo_total}")
print(f"\nBuilt-in Bots:")
for bot, pts in sorted(bot_totals.items(), key=lambda x: -x[1]):
    print(f"  {bot:12s}: {pts}")
