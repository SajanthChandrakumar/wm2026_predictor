import sys, os
sys.path.insert(0, os.path.abspath('src'))
from src.api import global_odds_engine
from collections import defaultdict

data = global_odds_engine.get_world_cup_odds(market='h2h')
graph = defaultdict(set)
for m in data:
    h = m['home_team']
    a = m['away_team']
    graph[h].add(a)
    graph[a].add(h)

visited = set()
groups = []
for node in graph:
    if node not in visited:
        comp = set()
        stack = [node]
        while stack:
            curr = stack.pop()
            if curr not in comp:
                comp.add(curr)
                visited.add(curr)
                stack.extend(graph[curr] - comp)
        groups.append(sorted(list(comp)))

print(len(groups))
for idx, g in enumerate(sorted(groups, key=lambda x: x[0])):
    print(f"Group {chr(65+idx)}: {g}")
