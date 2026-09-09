# Task 4 Report: UCL league table and full tournament simulation

## Result

Implemented the UCL 36-team league table, position-dependent playoff/R16
bracket, two-leg knockout simulation, single-leg final, and deterministic
seeded output on `codex/ucl2026`. The existing World Cup simulator remains the
default for WC requests and its response contract is unchanged.

## RED evidence

Focused command before the production module existed:

```text
.venv/bin/python -m pytest test_task4_ucl.py -q
```

Output:

```text
ImportError while importing test module 'test_task4_ucl.py'
ModuleNotFoundError: No module named 'src.services.ucl_simulation'
```

The tests were written first and cover schedule invariants, the complete
ranking order, ESPN display ordering, playoff leg hosts, seeded reproducibility,
explicit missing-model status, and aggregate ET/penalty advancement.

## GREEN evidence

Focused command:

```text
.venv/bin/python -m pytest test_task4_ucl.py -q
```

Output:

```text
20 passed in 0.69s
```

Full suite and static checks:

```text
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q src test_task4_ucl.py
git diff --check
```

Output:

```text
129 passed in 3.67s
```

## Implementation

- `src/services/ucl_simulation.py` validates 36 unique teams, 144 unique
  fixtures, eight fixtures per team, and four home/four away fixtures. It
  computes base points/goals/wins first, then opponent aggregates, lower
  disciplinary score, and the versioned higher UEFA coefficient tie-break.
  ESPN's supplied official order is available for live display while local
  ranking remains the simulation source.
- The fixed position path exposes 9/10 vs 23/24, 11/12 vs 21/22, 13/14 vs
  19/20, and 15/16 vs 17/18 playoff ties, with seeded clubs hosting the second
  leg. It continues through the position-banded R16, two-leg QF/SF, and
  single-leg final.
- Open fixtures sample their stored score matrix with `numpy.random.Generator`
  and default to exactly 20,000 runs with seed `20260908`; completed scores are
  copied unchanged. Task 3's `MatchContext`, aggregate ET eligibility, and
  penalty advancement helpers are reused. Missing valid matrices return an
  explicit `unavailable` result without synthetic ratings.
- Results include run/seed/status metadata, expected points/rank, Top-8,
  Top-24, R16, QF, SF, final, and champion percentages, plus bracket metadata.
- `src/routes/simulate.py` adds cache-only `/api/simulate_ucl` and routes
  `competition=ucl2026` through it while preserving WC `/api/simulate_knockout`.
- `test_task4_ucl.py` contains the focused red-green coverage.

## Self-review and concerns

- No provider calls or new dependencies were added. The route reads only the
  competition-scoped fixture cache; missing/invalid model inputs stay explicit.
- Future fixtures add no disciplinary events, so future discipline remains
  tied across runs. Completed fixture cards and supplied disciplinary scores
  are included in local rows.
- A global/default score matrix is accepted for future knockout pairings; when
  it is absent and no pair-specific matrix exists, the simulation returns
  `unavailable` instead of deriving a rating.
- A 50-run production-shaped smoke run completed in 0.79 seconds; the exact
  20,000-run default was not executed in the test suite because focused tests
  intentionally use small run counts.
- Protected data files, `frontend-v2/dist`, and the original checkout were not
  modified.

## Review fixes: round 1

### RED

The review regressions were added before the fixes and initially failed during
collection because the required `PLAYOFF_POSITION_BANDS`/draw API did not yet
exist:

```text
.venv/bin/python -m pytest test_task4_ucl.py -q
```

```text
ImportError: cannot import name 'PLAYOFF_POSITION_BANDS'
```

The added cases also cover both legal draw outcomes, forbidden cross-band
pairings, R16 band assignment, probability accounting, real cached match
shape, metadata propagation, invalid schedules, and completed fixtures with a
missing score.

### GREEN

Focused command:

```text
.venv/bin/python -m pytest test_task4_ucl.py -q
```

Output:

```text
26 passed in 0.76s
```

Full verification:

```text
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q src test_task4_ucl.py
git diff --check
```

Output:

```text
135 passed in 3.62s
```

### Fixes applied

- Replaced fixed playoff pairs with seeded random permutations inside the four
  official bands. R16 pairing also randomizes the permitted top-seed and
  playoff-winner assignments within each band; concrete draw slots flow into
  QF/SF metadata, and seeded clubs host their second legs.
- Added cache preparation that normalizes fixture-level `matrix`/
  `score_matrix` fields, preserves an explicit cached default, or averages
  valid open-fixture matrices into a normalized data-derived default for
  dynamic knockout matchups.
- Simulation and route boundaries now return explicit `unavailable` payloads
  for empty/invalid schedules, malformed fixtures, missing matrices, and
  completed fixtures without valid scores.
- The route passes cached discipline, UEFA coefficients/ranks, coefficient
  version, official order, and provenance to the simulator. Missing coefficient
  inputs produce a quality warning instead of treating lexical order as an
  official ranking.

### Self-review and concerns

- WC simulation paths and responses remain unchanged; UCL uses the new route
  branch only for `competition=ucl2026`.
- The returned bracket contains allowed band metadata plus a seeded sample
  draw; per-run outcomes use the same RNG draw that drives advancement, so
  probability accounting remains Top-8 800%, Top-24 2400%, R16 1600%, QF
  800%, SF 400%, final 200%, and champion 100% across teams.
- No live provider calls, new dependencies, protected data files, or
  `frontend-v2/dist` changes were introduced.
