# Task 5 report

## Status

Implemented competition-aware frontend integration for WC 2026 and UCL 2026/27. The default UI selection is UCL, valid selection is persisted under `competition`, all scoped API calls/query keys/invalidation include the active competition, and the KO toggle was removed from the client match flow.

## RED / GREEN

- RED: `node --test tests/competition-api.test.mjs` failed before implementation because `src/lib/competition.mjs` did not exist (`ERR_MODULE_NOT_FOUND`).
- GREEN: the same command passes after implementation: 2 tests passed, 0 failed.

## Verification

- `npx tsc -b`: passed.
- `npm run lint` (`oxlint src`): passed; only existing Fast Refresh warnings remain in `PageTransition.tsx` and `AppState.tsx`.
- `npm run build`: passed; Vite emitted only the existing large-chunk warning. Generated `frontend-v2/dist` artifacts were restored and are not part of this task.
- `git diff --check`: passed.
- `python3 -m pytest -q`: blocked during collection by the host Python 3.14 environment (NumPy symbol error and incompatible x86_64 `pydantic_core`), not by a test assertion.

## Self-review

- Competition selector uses `/api/competitions`, defaults invalid/missing storage to `ucl2026`, and keeps team selections isolated per competition.
- Dashboard, Value Bets, Edge, Team Form, Performance/Build-a-Bot, groups/table, detail, and simulator consume competition-scoped hooks.
- UCL groups view renders the ranked 36-team API table when available, with a fixture-team fallback; WC groups remain unchanged.
- UCL simulator calls `/simulate_ucl` and renders expected points/rank, Top 8/24, R16, QF, SF, final, champion, bracket, warnings, and provenance metadata; WC simulator remains intact.
- Match detail uses server context, displays model/pool tips separately, visibly marks unavailable source/pool data, supports documented pool context fields, and uses safe logo fallbacks.
- Backend adds ESPN logo fields and permits only `https://a.espncdn.com` in `img-src`.

## Review fix round 1

### RED / GREEN

- RED: extended `node --test tests/competition-api.test.mjs` failed at collection with `ERR_MODULE_NOT_FOUND` for the new pure helpers (`customBot.mjs`, `standings.mjs`, and `prediction.mjs`) before implementation.
- GREEN: the extended suite now passes: 5 tests passed, 0 failed. It covers clean/saved bot form state, exact 36-row unique ranked UCL standings validation (including whitespace-duplicate teams), and empty/all-zero/usable score matrices.

### Verification

- `node --test tests/competition-api.test.mjs`: passed (5/5).
- `npx tsc -b`: passed.
- `npm run lint` (`oxlint src`): passed; only the existing Fast Refresh warnings in `PageTransition.tsx` and `AppState.tsx` remain.
- `npm run build`: passed; only the existing Vite large-chunk warning was emitted. Generated `frontend-v2/dist` artifacts were restored immediately afterward.
- `git diff --check`: passed.

### Self-review

- `BuildABot` now reloads competition-scoped saved values/defaults when `customBot` or the active competition changes, clears stale simulation state, and ignores late simulation responses from a prior scope; the debounced simulation effect includes competition in its dependencies.
- UCL standings now render only when the API supplies exactly 36 rows with unique non-empty team names and unique ranks 1–36. Partial/empty/fixture-only data is explicitly unavailable; missing statistics display an em dash rather than fabricated zeros.
- Empty or all-zero prediction matrices are explicitly unavailable and cannot render an all-zero heatmap.
