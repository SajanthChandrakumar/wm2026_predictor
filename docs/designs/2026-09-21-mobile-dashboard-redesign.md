# Mobile Dashboard Redesign

## Goal

Make the UCL predictor immediately understandable on a phone, including for older or inexperienced users, without removing the detailed analytics already available elsewhere in the app.

## Approved direction

Use the approved “Spieltag zuerst” layout as the UCL dashboard:

- The next matches are the primary content.
- Each match is a large, tappable card with kickoff time, both teams, the model tip, a plain-language favorite statement, and a transparent data-source label.
- Detailed probabilities and 1/X/2 prices remain visible on wider screens and in match details; the mobile dashboard uses progressive disclosure instead of leading with dense numbers.
- The primary mobile navigation contains only `Spiele`, `Meine Tipps`, and `Mehr`.
- Existing secondary views remain reachable through `Mehr` and through the desktop sidebar.

## Visual language

- Background: cool neutral gray (`#edf1f6` light, deep navy-black in dark mode).
- Primary accent: cobalt blue (`#315efb`).
- Text: deep navy (`#111827`) with accessible muted gray.
- Urgent/open states: restrained orange (`#e75b20`).
- Confirmed/current data source: restrained green.
- Cards are opaque with subtle borders and shadows. Remove the blueprint grid, emerald glow, glass blur, and trading-terminal styling.
- Body text is at least 16px in match content. Interactive controls are at least 44px high; primary mobile controls target 48px or more.

## Responsive shell

- Desktop (`lg` and above): keep the full sidebar and all existing routes.
- Mobile/tablet (below `lg`): replace the sidebar block with a compact top bar and a fixed three-item bottom navigation.
- `Mehr` opens the existing secondary destinations and settings without inventing a second routing system.
- Account/provider diagnostics and refresh controls must not dominate the mobile home screen.

## Dashboard behavior

- Preserve the current upcoming/played split and match-detail navigation.
- Keep real bookmaker odds and Elo model odds distinct. Never relabel a model value as a bookmaker price.
- Match cards use existing match fields only; no fake teams, odds, freshness, or provider state.
- When no prediction exists, show an explicit unavailable state rather than a fabricated recommendation.
- Keep loading, error, and empty states readable on mobile.

## Scope

This pass changes the shared visual tokens, responsive application shell, mobile navigation, dashboard header/tabs, and dashboard match presentation. It does not redesign every analytics screen, alter APIs, change prediction logic, or add dependencies.

## Acceptance criteria

- At 320px width, the dashboard has no horizontal overflow and primary text remains readable.
- Mobile users see a compact header, match cards, and a three-item bottom navigation.
- Desktop users retain the full sidebar and access to every existing route.
- Match cards preserve team logos, kickoff time, top tip, source provenance, and navigation to details.
- The UI uses the approved cobalt/navy/orange/neutral palette in light and dark modes.
- Reduced-motion behavior remains intact.
- `node --test tests/*.test.mjs`, `npm run typecheck`, `npm run build`, and `npm run lint` pass in `frontend-v2`.

