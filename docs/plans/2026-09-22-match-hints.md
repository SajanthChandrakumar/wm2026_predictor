# Automatic Match Hints Implementation Plan

> **For agentic workers:** Execute this plan task-by-task with test-first development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Explain every available model tip with a short, truthful confidence statement and up to two evidence-based reasons on the mobile dashboard and match detail page.

**Architecture:** Add one pure TypeScript function that converts the existing `Match` payload into a structured `MatchHint`. A shared React component renders that structure in both existing views, so wording, confidence, source labeling, and unavailable behavior cannot diverge. No backend, API, model, or dependency changes are required.

**Tech Stack:** TypeScript 6, React 19, Tailwind CSS 4, Vite 8, Node 26 built-in test runner.

**Spec:** `docs/designs/2026-09-22-match-hints.md`

## Global Constraints

- Version 1 must not call an external AI or LLM API.
- The hint explains the existing tip and must never calculate or store a replacement tip.
- Bookmaker probabilities have priority; model probabilities are valid only for `source_mode === 'elo-only'`.
- Never label Elo values as bookmaker data and never invent missing values or reasons.
- Render at most two reasons and at most two sentences in the visible summary.
- Reuse one hint function and one rendering component in dashboard and detail.
- Add no dependency and change no backend, API response, database, prediction, odds, or tip logic.
- Preserve the current 320px/390px mobile layout and existing desktop presentation.
- Commit the rebuilt `frontend-v2/dist`, because FastAPI serves that directory directly.

---

### Task 1: Deterministic match-hint engine

**Files:**
- Create: `frontend-v2/src/lib/matchHint.ts`
- Create: `frontend-v2/tests/match-hint.test.mjs`

**Interfaces:**
- Consumes: `Match` and `Probabilities` from `frontend-v2/src/lib/types.ts`; `computeImpliedProbs` from `frontend-v2/src/lib/util.ts`.
- Produces: `MatchHintConfidence`, `MatchHintSource`, `MatchHint`, and `buildMatchHint(match: Match): MatchHint`.

- [ ] **Step 1: Write the failing unit tests**

Create `frontend-v2/tests/match-hint.test.mjs`. Import the TypeScript module directly; Node 26 strips erasable TypeScript syntax.

```js
import test from 'node:test'
import assert from 'node:assert/strict'
import { buildMatchHint } from '../src/lib/matchHint.ts'

const match = (overrides = {}) => ({
  id: 'm1',
  home_team: 'Bayern Munich',
  away_team: 'Arsenal',
  home_disp: 'Bayern',
  away_disp: 'Arsenal',
  top_tip: '2:1',
  max_xp: 4.2,
  raw_match: {},
  ...overrides,
})

test('uses margin-free bookmaker probabilities before model probabilities', () => {
  const hint = buildMatchHint(match({
    odds: { home: 1.5, draw: 4.5, away: 7 },
    probabilities: { home: 0.1, draw: 0.2, away: 0.7 },
    source_mode: 'odds+elo',
  }))
  assert.equal(hint.source, 'bookmaker')
  assert.equal(hint.sourceLabel, 'Buchmacherquote')
  assert.equal(hint.confidence, 'high')
  assert.match(hint.summary, /^Bayern ist klarer Favorit\./)
})

test('uses model probabilities only for elo-only matches', () => {
  const hint = buildMatchHint(match({
    probabilities: { home: 0.48, draw: 0.27, away: 0.25 },
    source_mode: 'elo-only',
  }))
  assert.equal(hint.source, 'elo')
  assert.equal(hint.sourceLabel, 'Elo-Modellquote · nicht wettbar')
  assert.equal(hint.confidence, 'medium')
  assert.match(hint.summary, /^Bayern ist leichter Favorit\./)
})

test('returns an explicit unavailable hint instead of guessing', () => {
  const hint = buildMatchHint(match({ source_mode: 'unavailable' }))
  assert.deepEqual(hint, {
    available: false,
    summary: 'Für eine verständliche Erklärung fehlen derzeit ausreichende Daten.',
    confidence: 'unavailable',
    confidenceLabel: 'Nicht verfügbar',
    source: 'unavailable',
    sourceLabel: 'Nicht verfügbar',
    reasons: [],
  })
})

test('classifies a narrow probability spread as low confidence', () => {
  const hint = buildMatchHint(match({
    probabilities: { home: 0.39, draw: 0.31, away: 0.30 },
    source_mode: 'elo-only',
  }))
  assert.equal(hint.confidence, 'low')
  assert.equal(hint.summary, 'Das Spiel ist sehr ausgeglichen.')
})

test('describes draw as the most likely single outcome without team reasons', () => {
  const hint = buildMatchHint(match({
    probabilities: { home: 0.3, draw: 0.42, away: 0.28 },
    source_mode: 'elo-only',
    xg_home: 2,
    xg_away: 1,
    home_form: { form: ['W'], on_fire: true },
  }))
  assert.equal(hint.summary, 'Ein Unentschieden ist der wahrscheinlichste einzelne Ausgang.')
  assert.deepEqual(hint.reasons, [])
})

test('keeps at most two aligned reasons in priority order', () => {
  const hint = buildMatchHint(match({
    probabilities: { home: 0.62, draw: 0.23, away: 0.15 },
    source_mode: 'elo-only',
    xg_home: 1.84,
    xg_away: 1.22,
    home_form: { form: ['W', 'W', 'W'], on_fire: true },
    away_form: { form: ['L'], on_fire: false },
    elo_home_share: 0.64,
  }))
  assert.equal(hint.reasons.length, 2)
  assert.equal(hint.reasons[0], 'Torerwartung: Bayern 1.84 zu Arsenal 1.22.')
  assert.equal(hint.reasons[1], 'Bayern kommt mit der stärkeren aktuellen Form.')
  assert.equal(hint.summary, 'Bayern ist klarer Favorit. Torerwartung: Bayern 1.84 zu Arsenal 1.22.')
})

test('uses Elo, absences, and knockout context only when their exact conditions match', () => {
  const elo = buildMatchHint(match({
    probabilities: { home: 0.2, draw: 0.25, away: 0.55 }, source_mode: 'elo-only', elo_home_share: 0.35,
  }))
  assert.equal(elo.reasons[0], 'Club-Elo sieht Arsenal bei 65 % im direkten Stärkevergleich.')

  const absencesAndKo = buildMatchHint(match({
    probabilities: { home: 0.6, draw: 0.22, away: 0.18 }, source_mode: 'elo-only',
    lineup_diff: {
      'Bayern Munich': { starters: {}, missing: [] },
      Arsenal: { starters: {}, missing: ['A', 'B'] },
    },
    is_ko_phase: true, first_leg_score: '1:1',
  }))
  assert.deepEqual(absencesAndKo.reasons, [
    'Beim Gegner sind mehr fehlende Spieler gemeldet.',
    'Das Hinspielergebnis kann den Spielverlauf stärker beeinflussen.',
  ])
})
```

- [ ] **Step 2: Run the focused test and verify RED**

Run from `frontend-v2`:

```bash
node --test tests/match-hint.test.mjs
```

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `src/lib/matchHint.ts`.

- [ ] **Step 3: Implement the pure engine**

Create `frontend-v2/src/lib/matchHint.ts` with the exact exported types from the spec. Import with explicit `.ts` extensions so Node and Vite resolve the same module:

```ts
import type { Match, Probabilities } from './types.ts'
import { computeImpliedProbs } from './util.ts'

export type MatchHintConfidence = 'high' | 'medium' | 'low' | 'unavailable'
export type MatchHintSource = 'bookmaker' | 'elo' | 'unavailable'

export interface MatchHint {
  available: boolean
  summary: string
  confidence: MatchHintConfidence
  confidenceLabel: 'Hoch' | 'Mittel' | 'Niedrig' | 'Nicht verfügbar'
  source: MatchHintSource
  sourceLabel: 'Buchmacherquote' | 'Elo-Modellquote · nicht wettbar' | 'Nicht verfügbar'
  reasons: string[]
}
```

Implement small private helpers for display names, finite-number checks, selected probabilities, favorite selection, reason candidates, and the unavailable constant. Apply these exact rules:

```ts
const confidence = top >= 0.55 && gap >= 0.15
  ? 'high'
  : top >= 0.43 && gap >= 0.08
    ? 'medium'
    : 'low'

const reasons = candidateReasons.slice(0, 2)
const summary = teamFavorite && confidence !== 'low' && reasons[0]
  ? `${lead} ${reasons[0]}`
  : lead
```

Generate team reasons only for a home/away favorite. Accept xG at absolute difference `>= 0.35`, favored-team-only `on_fire`, Elo deviation `>= 0.10`, opponent absence advantage `>= 2`, and the neutral K.-o. condition from the spec. Use `toFixed(2)` for xG and `Math.round(share * 100)` for Elo.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
node --test tests/match-hint.test.mjs
```

Expected: 7 tests pass.

- [ ] **Step 5: Run typecheck and commit the engine**

Run:

```bash
npm run typecheck
git diff --check
```

Then commit only the two task files:

```bash
git add frontend-v2/src/lib/matchHint.ts frontend-v2/tests/match-hint.test.mjs
git commit -m "feat(ui): add deterministic match hints"
```

---

### Task 2: Shared hint UI in dashboard and detail

**Files:**
- Create: `frontend-v2/src/components/shared/MatchHintCard.tsx`
- Modify: `frontend-v2/src/features/dashboard/FixtureRow.tsx`
- Modify: `frontend-v2/src/features/detail/DetailView.tsx`
- Modify: `frontend-v2/tests/mobile-dashboard-ui.test.mjs`
- Rebuild and commit: `frontend-v2/dist/index.html`, `frontend-v2/dist/assets/index-*.js`, `frontend-v2/dist/assets/index-*.css`

**Interfaces:**
- Consumes: `buildMatchHint(match: Match): MatchHint` from Task 1.
- Produces: `MatchHintCard({ match }: { match: Match })`, rendered by both existing views.

- [ ] **Step 1: Write the failing integration contract**

Append to `frontend-v2/tests/mobile-dashboard-ui.test.mjs`:

```js
test('dashboard and detail share the automatic hint component', () => {
  const card = read('src/components/shared/MatchHintCard.tsx')
  const dashboard = read('src/features/dashboard/FixtureRow.tsx')
  const detail = read('src/features/detail/DetailView.tsx')

  assert.match(card, /buildMatchHint/)
  assert.match(card, /Sicherheit/)
  assert.match(card, /<details/)
  assert.match(card, /Warum\?/)
  assert.match(card, /min-h-11/)
  assert.match(dashboard, /<MatchHintCard match=\{match\}/)
  assert.match(detail, /<MatchHintCard match=\{match\}/)
})
```

- [ ] **Step 2: Run the integration test and verify RED**

Run:

```bash
node --test tests/mobile-dashboard-ui.test.mjs
```

Expected: FAIL because `MatchHintCard.tsx` does not exist.

- [ ] **Step 3: Implement the shared presentation**

Create `MatchHintCard.tsx` as a small presentational component:

- Call `buildMatchHint(match)` once.
- Render the summary at `text-base`.
- Render `Sicherheit: Hoch|Mittel|Niedrig` only when available.
- Map confidence colors: `high` to a restrained green class, `medium` to cobalt/`emerald-a`, `low` to `orange-a`.
- Keep `sourceLabel` visible and unchanged.
- Render `<details>` only when `reasons.length > 0`; its `<summary>` text is `Warum?` and includes `min-h-11`.
- List the existing reason strings; do not recompute or reinterpret them in React.
- For unavailable data, render only the unavailable summary and source.

Modify `FixtureRow.tsx`:

- Remove `PredictionDetails`, `predictionDetails`, `favoriteStatement`, and the now-unused probability imports.
- Change the outer `motion.button` to a non-interactive `motion.div`, and put the existing fixture navigation content in its own full-width button.
- Keep the existing `Unser Tipp`, top-tip badge, played score, and mobile container.
- Render `<MatchHintCard match={match} />` outside the navigation button so the native `details` disclosure is valid HTML and can be opened without navigating away.
- Preserve the existing desktop row, keyboard navigation, 48 px touch targets, and mobile trailing content.

Modify `DetailView.tsx`:

- Import the shared component.
- Render `<MatchHintCard match={match} />` after the lineup alert and before the quantitative two-column grid.
- Do not alter prediction requests, quote presentation, adoption, pool context, bots, or heatmap logic.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
node --test tests/match-hint.test.mjs tests/mobile-dashboard-ui.test.mjs
npm run typecheck
```

Expected: all focused tests pass and TypeScript exits 0.

- [ ] **Step 5: Run complete verification and rebuild the served app**

Run from `frontend-v2`:

```bash
node --test tests/*.test.mjs
npm run typecheck
npm run build
npm run lint
```

Run from the repository root:

```bash
pytest -q
git diff --check
```

Expected: all test commands exit 0. Existing non-failing Vite chunk-size and Fast Refresh lint warnings may remain unchanged.

- [ ] **Step 6: Browser acceptance at 390px**

Serve the rebuilt FastAPI app and verify with real `ucl2026` data:

- an available match shows the model tip, confidence badge, summary, and truthful source;
- `Warum?` expands to one or two reasons and is keyboard operable;
- a match without a valid source shows the explicit unavailable sentence and no empty disclosure;
- opening a match shows the same summary in the detail view;
- document width does not exceed the viewport and the console has no new errors.

- [ ] **Step 7: Commit the UI and generated release bundle**

Stage only the shared component, two view changes, regression test, and current build output:

```bash
git add frontend-v2/src/components/shared/MatchHintCard.tsx frontend-v2/src/features/dashboard/FixtureRow.tsx frontend-v2/src/features/detail/DetailView.tsx frontend-v2/tests/mobile-dashboard-ui.test.mjs frontend-v2/dist
git commit -m "feat(ui): explain match tips in plain language"
```
