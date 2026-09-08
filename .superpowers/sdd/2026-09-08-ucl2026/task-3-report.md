# Task 3 Report: Central prediction, pool strategy, and extra time

## Result

Implemented the shared competition-aware prediction service and routed match
predictions, `/api/predict`, freeze, and archive reconstruction through it.
The implementation keeps WC scoring and legacy `top_tip` compatibility while
removing UCL synthetic-rating and client-KO shortcuts.

## RED evidence

Focused command before the production service existed:

```text
.venv/bin/python -m pytest test_task3_prediction.py -q
```

Expected collection failure:

```text
ModuleNotFoundError: No module named 'src.services.prediction'
```

The focused tests were written first and use real score-matrix/math behavior,
captured in-memory snapshots, and no live provider calls.

## GREEN evidence

Focused command:

```text
.venv/bin/python -m pytest test_task3_prediction.py -q
```

Output:

```text
9 passed in 0.63s
```

Full Python suite and syntax check:

```text
.venv/bin/python -m compileall -q src test_task3_prediction.py
.venv/bin/python -m pytest -q
git diff --check
```

Output:

```text
94 passed in 2.93s
```

## Files changed

- `src/services/prediction.py` — central source-aware model pipeline,
  normalized match context, exact UCL stage/leg extra-time eligibility,
  conditional 30-minute Poisson convolution, separate penalty advancement,
  model/pool output, T-15 freeze persistence/idempotency, T-5 helper, and
  compatibility adapters.
- `src/services/predictions.py` — plural import compatibility for integrations.
- `src/routes/predict.py` — `/api/predict` now uses the shared service, exposes
  model/pool/context output, and adds `/api/freeze` plus `/api/predict/freeze`.
- `src/routes/matches.py` — cached-edge and fixture prediction integration,
  UCL no-rating behavior, model/pool/source/context fields, and archive input
  provenance.
- `src/services/elo_sync.py` — reconstruction now uses the shared service,
  retaining WC historical fallback and explicit UCL unavailable state.
- `src/routes/pool.py` — competition-scoped `GET/PUT
  /api/pool-context/{match_id}` persistence with strict score-context field
  validation and pool-only invalid-count handling.
- `src/api.py` — pool router registration, PUT CORS support, and T-5 user-tip
  closure with permissive undated legacy compatibility.
- `test_task3_prediction.py` — red-green coverage for context rules, AET,
  penalties, pool lambda/field optimization, source output, freeze behavior,
  and user-tip closure.

## Self-review

- UCL stages are limited to `league`, `playoff`, `round_of_16`,
  `quarterfinal`, `semifinal`, and `final`; legs are limited to `single`,
  `first`, and `second`.
- First legs never trigger ET; second legs trigger only aggregate ties; finals
  trigger only 90-minute draws. The matrix is normalized after conditional ET
  convolution, and penalties are represented only by a separate 50/50
  advancement result.
- `top_tip` is always the model/xP tip and remains separate from `pool_tip`.
  Invalid, empty, or all-zero field counts return only pool unavailability.
- T-15 freeze selects the latest eligible snapshot using
  `select_t15_snapshot`, persists all derived inputs atomically, and returns
  the stored result on repeat calls.
- `/api/predict` and cached UCL edge enrichment never call synthetic Elo
  fallbacks; odds-only and Elo-only remain explicit source modes.
- Existing WC routes and SRF scoring tests remain green. No provider calls or
  new dependencies were added.
- Protected data files, `frontend-v2/dist`, and the original checkout were not
  modified.

## Concerns

- The score matrix keeps the existing bounded goal dimensions and conditions
  Poisson increments on representable cells; this preserves exact matrix
  normalization and UI shape while the existing 0–10 range makes discarded
  tails negligible.
- The pool-context route stores manually entered counts and reuses them at
  freeze; live recalculation of a pool tip still requires the shared model
  prediction input, as intended by the service boundary.

## Review fixes: round 1

### RED

Focused regression command before the fixes:

```text
.venv/bin/python -m pytest test_task3_prediction.py -q
```

Output:

```text
8 failed, 9 passed in 1.04s
```

The failures covered pool-result mapping/source-status preservation, freeze
compare-and-set and concurrent user-tip preservation, top-level prediction
context, pool-context invalidation, competition-aware T-5 validation, first-
leg extra-time rejection, full reconstruction context/model aliases, central
honest-tip rebuilding, and UCL cached-edge provenance/legacy-edge clearing.

### GREEN

Focused regression command after the fixes:

```text
.venv/bin/python -m pytest test_task3_prediction.py -q
```

Output:

```text
21 passed in 1.19s
```

Required full-suite and static checks:

```text
.venv/bin/python -m compileall -q src test_task3_prediction.py
.venv/bin/python -m pytest -q
git diff --check
```

Output:

```text
106 passed in 3.50s
```

### Fixes applied

- Mapped pool-service fields explicitly to `pool_tip`, `pool_status`, lambda,
  and metrics without overwriting the top-level source status; freeze now
  persists the actual pool tip.
- Replaced freeze read/replace with a Mongo-compatible conditional update on
  missing `prediction.frozen_at`; losers reload the winner and only prediction
  freeze fields are written, preserving concurrent user/archive updates.
- Accepted documented top-level context fields, automatically loaded scoped
  pool context in matches/prediction routes, and cleared archived derived pool
  fields when pool context changes.
- Made missing/invalid kickoff permissive only for legacy WC, rejected first-leg
  extra time before final-stage checks, and preserved stale/failed source
  status and provenance.
- Routed honest-tip rebuilding through `PredictionService`; reconstruction now
  preserves full context and writes both `model_tip` and legacy `top_tip` plus
  source/provenance, with no UCL single-leg shortcut.
- Recomputed UCL cached edges only from explicit valid ratings and cleared
  unavailable legacy edge values; removed the unused broad import-star shim.

### Self-review and concerns

- The conditional freeze update uses only dotted `prediction.*` `$set` fields,
  so it cannot overwrite a concurrent `user_tip`; the race fake exercises the
  losing-writer reload path. Production Mongo semantics are required for the
  atomic predicate/update guarantee.
- Pool-derived fields are intentionally invalidated on context PUT rather than
  guessed from incomplete inputs; they are regenerated by the shared service
  when complete model inputs are available.
- The bounded score-matrix representation retains non-trigger probability mass
  in its original cells; extra-time-origin mass may aggregate into the same
  numeric final-score cell, then the matrix is normalized. Penalty advancement
  remains separate from the score matrix.
