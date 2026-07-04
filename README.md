# WM 2026 Predictor

<div align="center">

**A quantitative prediction engine and analytics dashboard for the FIFA World Cup 2026**

[**Live Demo**](https://wc2026-predictor-8skd.onrender.com/)

[![Tests](https://github.com/SajanthChandrakumar/wm2026_predictor/actions/workflows/test.yml/badge.svg)](https://github.com/SajanthChandrakumar/wm2026_predictor/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.12+-3776ab?style=flat&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat)]()

</div>

A full-stack quantitative prediction engine built for the [SRF Tippspiel](https://wmtippspiel.srf.ch) — a competitive closed prediction pool during the FIFA World Cup 2026. The system reverse-engineers bookmaker odds into Expected Goals, applies a Dixon-Coles–corrected bivariate Poisson model, blends in a live Elo rating system, and computes the mathematically optimal tip for each match.

> See [ARCHITECTURE.md](ARCHITECTURE.md) for the full mathematical derivation.

---

## Motivation

In a closed prediction pool, **maximising raw expected points is the wrong objective**. If everyone picks the chalk tip, you share points with the field even when you're right. The correct strategy is to maximise your *advantage over the field* — which sometimes means taking a calculated contrarian position.

This system implements that distinction: a chalk mode (maximise expected points) and a pool mode (maximise `E[advantage vs chalk] + λ · SD[advantage]`, where λ controls aggressiveness).

---

## ⚠️ Disclaimer

This project is developed **strictly for scientific, educational, and research purposes** as a companion tool for the [SRF Tippspiel](https://wmtippspiel.srf.ch) — a free, non-monetary prediction competition.

- The author **accepts no responsibility or liability** for any decisions made by third parties based on the output of this software.
- This tool does **not** constitute financial, investment, or betting advice.
- Using this software to place real-money wagers is entirely at the user's own risk and is explicitly **not** the intended use case.
- All probability estimates are model outputs subject to uncertainty and should never be treated as guaranteed outcomes.

By using this software you agree that the author cannot be held liable for any losses, damages, or legal consequences arising from its use.

---

## Technical Highlights

| Component | Detail |
|---|---|
| **Prediction model** | Dixon-Coles bivariate Poisson (ρ = −0.15); SciPy L-BFGS-B reverse-engineer solver for xG |
| **Fixtures & results** | ESPN public scoreboard — full played + upcoming fixture list, live scores, KO-round detection, group standings (no auth, no quota) |
| **Odds ingestion** | The Odds API — consensus **median** across all bookmakers (H2H + O/U 2.5) for upcoming games; ESPN/DraftKings odds as fallback; proportional margin removal |
| **Elo system** | Dynamic ratings for all 32 qualified nations; K = 60; margin-of-victory multiplier; +80 host bonus (USA/CAN/MEX) on post-match updates only |
| **Probability blend** | 70 % bookmaker odds / 30 % Elo, restricted to the win/loss pool — draw probability held fixed to prevent deflation |
| **K.O. phase** | Extra-time xG inflation weighted by P(draw after 90 min) — conditional, not a flat 1.33× multiplier |
| **xP optimiser** | Evaluates all 36 possible tips (0:0 – 5:5) against the full score matrix using the exact SRF Tippspiel scoring rules |
| **Pool strategy** | Contrarian objective: `E[advantage vs chalk] + λ · SD[advantage]`; λ = 0 reproduces chalk, λ ≈ 0.3 = soft contrarian, λ ≥ 0.5 = true draw gambles |
| **House bots** | Four fixed-strategy agents: Broker (pure market), Professor (pure Elo), X-Sniper (highest-xP draw), Zocker (weighted-random, seeded by match ID) |
| **Learning bots** | Three adaptive agents that evolve over the tournament: Optimizer (best historical params), Momentum (recency-weighted params), Mitläufer (follows current leader) |
| **Caching** | Dynamic TTL: >24 h to kick-off → 12 h; 2–24 h → 1 h; <2 h → 15 min. Learning bot results cached by archive signature — recomputes only when new results arrive |
| **Elo sync** | Idempotent daily background job (APScheduler, 04:00 UTC); tracks processed match IDs; warms all caches post-sync |

---

## Screenshots

<details>
<summary><strong>Score Matrix — Dixon-Coles bivariate Poisson heatmap</strong></summary>

![Score Matrix](docs/screenshot_matrix.png)
</details>

<details>
<summary><strong>Performance View — You vs Algo head-to-head & bot scoreboard</strong></summary>

![Performance View](docs/screenshot_performance.png)
</details>

<details>
<summary><strong>Build-a-Bot — design your own tipping strategy</strong></summary>

![Build-a-Bot](docs/screenshot_build_a_bot.png)
</details>

<details>
<summary><strong>Dashboard — live fixtures with probabilities and algo tips</strong></summary>

![Dashboard](docs/screenshot_dashboard.png)
</details>

---

## Dashboard Views

| View | Description |
|---|---|
| **Dashboard** | All tournament fixtures grouped by day with live probabilities, algo tips, and team form badges |
| **Top Value Bets** | Fixtures ranked by Expected Points — highest xP tip first |
| **Model Edge** | Where Elo diverges most from market consensus — visualised as paired probability bars |
| **Team Form** | Per-team Elo trajectory across the tournament; compare up to 4 teams simultaneously |
| **Groups** | All 12 group standings dynamically computed from the completed-match archive — no extra API call |
| **Performance** | Full analytics: your SRF points, hit rate, You vs Algo head-to-head, bot scoreboard, cumulative points race, and editable match history |

---

## Performance & Tracking

The Performance view tracks parallel scoring streams in real time:

- **You** — manual tips entered via the inline editor
- **Algo** — the system's top-pick tip at prediction time; retroactively reconstructed from pre-match Elo baselines for matches played before the app started (flagged as `ALGO*`)
- **House Bots** — four fixed-strategy agents (Broker, Professor, X-Sniper, Zocker)
- **Learning Bots** — three adaptive agents that reveal what they "learned":

| Bot | Philosophy | What it shows |
|---|---|---|
| **Optimizer** | Best cumulative params over all completed matches | `Markt 50% · Risiko +0.5 · Draw +2` |
| **Momentum** | Best recency-weighted params (decay = 0.9) | `Markt 75% · Risiko 0` |
| **Mitläufer** | Copies the current house bot leader each match | `Folgt: Professor` |

The **bot scoreboard** ranks all agents by total points, average per match, and tendency accuracy. A cumulative points race chart shows how each strategy evolves over the tournament.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/matches` | All fixtures with odds, Elo, top tip, xP, and model edge; `?force=true` bypasses cache |
| `POST` | `/api/predict` | Full prediction for one match: xG, score matrix, ranked tips; accepts K.O. toggle |
| `GET` | `/api/archive` | Complete prediction archive: all matches, user tips, algo tips, bot tips, results, and points |
| `POST` | `/api/archive/user_tip` | Save or update a user tip; recalculates points if result is already known |
| `GET` | `/api/elo_history` | Per-team Elo snapshots across the tournament (powers Team Form chart) |
| `POST` | `/api/sync_elo` | Trigger an immediate Elo sync from completed match scores; warms all downstream caches |
| `GET` | `/api/quota` | Remaining requests for The Odds API (ESPN is unmetered) |
| `GET` | `/api/standings` | Group standings for all 12 WC 2026 groups; 1 h MongoDB cache |
| `GET` | `/api/learning_bots` | Current state of all three learning bots; signature-keyed cache (recomputes on new results) |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn, APScheduler |
| Math | NumPy, SciPy (`optimize.minimize`, L-BFGS-B), Pandas |
| Frontend | Vanilla ES modules — zero framework, zero build step |
| Charts | Chart.js (Elo trajectory, cumulative bot race) |
| Data | ESPN public API (fixtures, scores, standings, KO rounds), The Odds API (multi-bookmaker odds for upcoming games), MongoDB Atlas (archive, cache, bot states) |
| Design | Editorial-Minimal: Inter typography, flat surfaces, emerald accent (`#34d399`), CSS custom properties, fully responsive |

---

## Quick Start

```bash
# 1. Clone and enter
git clone https://github.com/SajanthChandrakumar/wm2026_predictor.git
cd wm2026_predictor

# 2. Virtual environment + dependencies
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Environment Variables
echo "ODDS_API_KEY=your_key_here" > .env
echo "MONGO_URI=mongodb+srv://..." >> .env

# 4. Start
uvicorn src.main:app --reload
```

Open **http://127.0.0.1:8000** in your browser.

---

## Tournament Operations

| Operation | How |
|---|---|
| **Auto Elo sync** | Runs daily at 04:00 UTC via APScheduler; warms learning bots + standings cache automatically |
| **Manual sync** | Press **Sync Elo Ratings** in the sidebar |
| **Idempotency** | MongoDB `archive` collection ensures each result is applied exactly once |
| **Cache control** | Dynamic TTL; press **Refresh Data** to force a live fetch (costs one API call) |
| **Learning bot cache** | Keyed by archive signature — auto-invalidates when new results arrive, never on a timer |

---

## Project Structure

```
wm2026_predictor/
├── src/
│   ├── api.py                       # FastAPI app: init, middleware, router wiring, small endpoints
│   ├── constants.py                 # Team-name maps, TTLs, KO-round detection
│   ├── math_engine.py               # Elo, xG solver, Dixon-Coles, xP, pool optimiser, bot tips
│   ├── learning_bots.py             # Optimizer / Momentum / Mitläufer — grid-search + follow-the-leader
│   ├── odds_engine.py               # The Odds API client; quota tracking
│   ├── odds_engine_apifootball.py   # Legacy API-Football client (unused; kept as fallback)
│   ├── routes/
│   │   ├── matches.py               # GET /matches — ESPN fixtures × Odds API hybrid, edge enrichment
│   │   ├── predict.py               # POST /predict — full single-match prediction
│   │   └── custom_bot.py            # Build-a-Bot save / simulate endpoints
│   └── services/
│       ├── espn_data.py             # ESPN fixtures, scores, standings (public, no quota)
│       ├── odds_helpers.py          # extract_odds (median), dynamic TTL, totals cache
│       ├── archive.py               # Load/upsert archive, ID-index resolution, signature
│       └── elo_sync.py              # perform_elo_sync — grading, backfills, cache warm-up
├── frontend/
│   ├── index.html                   # SPA shell (6 views + detail pane)
│   ├── style.css                    # Design system: Editorial-Minimal, CSS custom properties
│   └── js/
│       ├── main.js                  # Boot, view router, sidebar wiring
│       ├── api.js                   # Typed fetch wrappers for all endpoints
│       ├── state.js                 # Shared app state
│       ├── util.js                  # Formatting, probability helpers
│       └── views/
│           ├── dashboard.js         # Fixture grid + form badges
│           ├── value-bets.js        # xP-ranked fixture list
│           ├── edge.js              # Model vs market divergence
│           ├── team-form.js         # Elo history chart + team compare
│           ├── groups.js            # Group standings from archive
│           ├── performance.js       # Bot scoreboard, race chart, match history
│           └── detail.js            # Heatmap, tip ladder, bot tips
├── data/
│   └── elo_ratings.csv              # Live Elo ratings for all qualified teams
├── ARCHITECTURE.md                  # Full mathematical derivation
└── README.md
```

---

## Running Tests

```bash
.venv/bin/python -m pytest test_math_engine.py test_pool_optimizer.py test_build_a_bot.py -v
```

---

## Haftungsausschluss

Dieses Projekt ist ein Hobby- und Bildungsprojekt, das aus persönlichem Interesse an Data Science, Software-Architektur und Wahrscheinlichkeitsrechnung entwickelt wurde. Die generierten Daten und Expected-Points-Berechnungen dienen ausschließlich zu Informations- und Analysezwecken und stellen ausdrücklich **keine Anlage-, Finanz- oder Wettberatung** dar. Der Autor übernimmt keine Haftung für Verluste, die durch die Nutzung dieser Software entstehen.
