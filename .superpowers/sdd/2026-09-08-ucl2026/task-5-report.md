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
