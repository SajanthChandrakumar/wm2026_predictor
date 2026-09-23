# Mobile Dashboard Redesign Implementation Plan

> **For agentic workers:** Implement this plan task-by-task using the requested subagent workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved mobile-first UCL dashboard and modern cobalt visual language while preserving every existing route and truthful odds provenance.

**Architecture:** Reuse the existing React Router shell and match query. Adapt the shared CSS tokens and responsive shell, then render the existing match data as accessible mobile cards while retaining the denser desktop row. No API or data-model changes are required.

**Tech Stack:** React 19, React Router, TypeScript, Tailwind CSS 4, Vite, Node test runner.

**Spec:** `docs/designs/2026-09-21-mobile-dashboard-redesign.md`

## Global Constraints

- Do not add dependencies.
- Do not alter backend APIs, prediction logic, match types, or stored data.
- Preserve the semantic difference between bookmaker odds, Elo model odds, and unavailable data.
- Preserve all existing routes on desktop and keep them reachable from mobile `Mehr`.
- Support a 320px viewport without horizontal overflow.
- Do not stage or modify `data/elo_history.json` or `data/elo_ratings.csv`.
- Follow the existing project structure; avoid speculative components and abstractions.

---

### Task 1: Responsive shell and mobile-first dashboard

**Files:**
- Create: `frontend-v2/tests/mobile-dashboard-ui.test.mjs`
- Modify: `frontend-v2/src/index.css`
- Modify: `frontend-v2/src/components/layout/AppShell.tsx`
- Modify: `frontend-v2/src/components/layout/Sidebar.tsx`
- Modify: `frontend-v2/src/features/dashboard/DashboardView.tsx`
- Modify: `frontend-v2/src/features/dashboard/FixtureRow.tsx`
- Optionally modify only if reuse makes the implementation smaller: `frontend-v2/src/components/shared/Badges.tsx`, `frontend-v2/src/components/shared/ProbBar.tsx`

**Interfaces:**
- Consumes: existing `useMatches()`, `Match`, `TeamLabel`, `TipBadge`, `ProbBar`, React Router routes.
- Produces: the same route and data behavior with a responsive shell and accessible mobile match-card presentation.

- [ ] **Step 1: Write the failing source-level regression test**

Create `frontend-v2/tests/mobile-dashboard-ui.test.mjs` with Node's built-in test runner. Read the source files with `node:fs` and assert these durable contracts:

```js
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')

test('mobile shell exposes the approved three-item navigation', () => {
  const shell = read('src/components/layout/AppShell.tsx')
  assert.match(shell, /Spiele/)
  assert.match(shell, /Meine Tipps/)
  assert.match(shell, /Mehr/)
  assert.match(shell, /lg:hidden/)
})

test('dashboard uses plain-language mobile prediction cards', () => {
  const row = read('src/features/dashboard/FixtureRow.tsx')
  assert.match(row, /Unser Tipp/)
  assert.match(row, /Buchmacherquote|Elo-Modellquote|Nicht verfügbar/)
  assert.match(row, /min-h-\[48px\]/)
})

test('global styling uses the approved palette and removes the blueprint grid', () => {
  const css = read('src/index.css')
  assert.match(css, /#315efb/i)
  assert.match(css, /#edf1f6/i)
  assert.doesNotMatch(css, /blueprint grid/i)
})
```

- [ ] **Step 2: Verify the test fails for the missing redesign**

Run: `node --test tests/mobile-dashboard-ui.test.mjs`

Expected: failures because the current shell lacks the three-item mobile navigation, fixture rows lack plain-language mobile copy, and the CSS still contains the blueprint-grid design.

- [ ] **Step 3: Implement the minimal responsive redesign**

Use existing components and routes. Required behavior:

- Replace visual tokens with the approved cobalt/navy/orange/cool-neutral palette for light and dark themes.
- Remove fixed background grids, emerald glows, top hairline effects, and heavy glass blur; keep existing utility class names where that minimizes the diff.
- Keep the desktop sidebar at `lg` and above. Hide it below `lg`.
- Add a compact mobile top bar and a fixed bottom bar in `AppShell` with exactly `Spiele`, `Meine Tipps`, and `Mehr`. `Spiele` routes to `/`, `Meine Tipps` routes to `/performance`, and `Mehr` exposes links to all remaining existing destinations plus competition/theme/refresh controls.
- Add bottom padding to mobile page content so the fixed navigation never covers the last card.
- Change the UCL dashboard heading to plain German copy centered on upcoming matches. Preserve upcoming/played switching.
- Render each fixture as a large mobile card with kickoff, vertically stacked home/away teams, top tip, provenance label, and a plain-language favorite statement derived only from existing probabilities or implied bookmaker probabilities. Render an explicit unavailable sentence when neither source is available.
- Preserve the current dense desktop layout and `ProbBar` presentation at `sm` and above where practical.
- Keep buttons and navigation targets at least 44px high; primary mobile card target at least 48px.

- [ ] **Step 4: Verify the focused test passes**

Run: `node --test tests/mobile-dashboard-ui.test.mjs`

Expected: 3 tests pass.

- [ ] **Step 5: Run the complete frontend verification**

Run from `frontend-v2`:

```bash
node --test tests/*.test.mjs
npm run typecheck
npm run build
npm run lint
```

Expected: every command exits 0.

- [ ] **Step 6: Commit only the redesign files**

```bash
git add docs/designs/2026-09-21-mobile-dashboard-redesign.md docs/plans/2026-09-21-mobile-dashboard-redesign.md frontend-v2/tests/mobile-dashboard-ui.test.mjs frontend-v2/src/index.css frontend-v2/src/components/layout/AppShell.tsx frontend-v2/src/components/layout/Sidebar.tsx frontend-v2/src/features/dashboard/DashboardView.tsx frontend-v2/src/features/dashboard/FixtureRow.tsx frontend-v2/src/components/shared/Badges.tsx frontend-v2/src/components/shared/ProbBar.tsx
git commit -m "feat(ui): add mobile-first match dashboard"
```

Before committing, omit unchanged optional files from `git add`. Confirm the two dirty Elo files are unstaged.
