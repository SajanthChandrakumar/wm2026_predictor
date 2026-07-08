# WM 2026 Predictor

<div align="center">

**A quantitative prediction engine and analytics dashboard for the FIFA World Cup 2026**

[**Live Demo**](https://wc2026-predictor-8skd.onrender.com/)

[![Tests](https://github.com/SajanthChandrakumar/wm2026_predictor/actions/workflows/test.yml/badge.svg)](https://github.com/SajanthChandrakumar/wm2026_predictor/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.12+-3776ab?style=flat&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61dafb?style=flat&logo=react)](https://react.dev/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat)](LICENSE)

</div>

A full-stack quantitative prediction engine built for the [SRF Tippspiel](https://wmtippspiel.srf.ch) — a competitive closed prediction pool during the FIFA World Cup 2026. The system reverse-engineers bookmaker odds into Expected Goals, applies a Dixon-Coles–corrected bivariate Poisson model, blends in a live Elo rating system, and computes the mathematically optimal tip for each match.

> See [ARCHITECTURE.md](ARCHITECTURE.md) for the full mathematical derivation.

---

## Motivation

In a closed prediction pool, **maximising raw expected points is the wrong objective**. If everyone picks the chalk tip, you share points with the field even when you're right. The correct strategy is to maximise your *advantage over the field* — which sometimes means taking a calculated contrarian position.

This system implements that distinction: a chalk mode (maximise expected points) and a pool mode (maximise `E[advantage vs chalk] + λ · SD[advantage]`, where λ controls aggressiveness).

---

## ⚠️ Disclaimer

This project is developed **strictly for scientific, educational, and research purposes** as a companion tool for the [SRF Tippspiel](https://wmtippspiel.srf.ch) — a free, non-monetary prediction competition. It does **not** constitute financial, investment, or betting advice; all probability estimates are model outputs subject to uncertainty. Using this software to place real-money wagers is entirely at the user's own risk and explicitly not the intended use case. The author accepts no liability for losses or damages arising from its use.

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
| **Monte Carlo simulator** | Full knockout-bracket simulation (default 20 000 runs) from live Elo ratings — per-team title odds and round-reach probabilities |
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
| **Performance** | Full analytics: your SRF points, hit rate, You vs Algo head-to-head, bot scoreboard, Build-a-Bot, cumulative points race, and editable match history |
| **K.O. Simulator** | Monte Carlo knockout-bracket simulation — title odds and round-reach probabilities per team |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/matches` | All fixtures with odds, Elo, top tip, xP, and model edge; `?force=true` bypasses cache |
| `POST` | `/api/predict` | Full prediction for one match: xG, score matrix, ranked tips; accepts K.O. toggle |
| `GET` | `/api/archive` | Complete prediction archive: all matches, user tips, algo tips, bot tips, results, and points |
| `POST` | `/api/archive/user_tip` | Save or update a user tip; recalculates points if result is already known |
| `GET/POST` | `/api/custom_bot` | Load / save the Build-a-Bot strategy |
| `POST` | `/api/custom_bot/simulate` | Backtest a bot parameter set against all completed matches |
| `GET` | `/api/simulate_knockout` | Monte Carlo knockout simulation; `?runs=` controls sample size |
| `GET` | `/api/elo_history` | Per-team Elo snapshots across the tournament (powers Team Form chart) |
| `GET` | `/api/elo_ratings` | Current Elo table for all qualified teams |
| `POST` | `/api/sync_elo` | Trigger an immediate Elo sync from completed match scores; warms all downstream caches |
| `GET` | `/api/learning_bots` | Current state of all three learning bots; signature-keyed cache |
| `GET` | `/api/standings` | Group standings for all 12 WC 2026 groups; 1 h MongoDB cache |
| `GET` | `/api/quota` | Remaining requests for The Odds API (ESPN is unmetered) |
| `GET` | `/api/ping` | Keep-alive endpoint (prevents Render free-tier cold starts) |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn, APScheduler |
| Math | NumPy, SciPy (`optimize.minimize`, L-BFGS-B), Pandas |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, React Router |
| Charts | Recharts (Elo trajectory, cumulative bot race, simulation odds) |
| Data | ESPN public API (fixtures, scores, standings, KO rounds), The Odds API (multi-bookmaker odds), MongoDB Atlas (archive, cache, bot states) |

---

## Quick Start

```bash
# 1. Clone and enter
git clone https://github.com/SajanthChandrakumar/wm2026_predictor.git
cd wm2026_predictor

# 2. Backend: virtual environment + dependencies
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Environment variables
echo "ODDS_API_KEY=your_key_here" > .env
echo "MONGO_URI=mongodb+srv://..." >> .env

# 4. Frontend: build the React app (FastAPI serves the dist/ folder)
cd frontend-v2 && npm install && npm run build && cd ..

# 5. Start
uvicorn src.api:app --reload
```

Open **http://127.0.0.1:8000**. For frontend development with hot reload, run `npm run dev` inside `frontend-v2` (proxies `/api` to port 8000).

---

## Project Structure

```
wm2026_predictor/
├── src/
│   ├── api.py            # FastAPI app: init, middleware, router wiring
│   ├── math_engine.py    # Elo, xG solver, Dixon-Coles, xP, pool optimiser
│   ├── learning_bots.py  # Adaptive agents (Optimizer / Momentum / Mitläufer)
│   ├── routes/           # matches, predict, custom_bot, simulate
│   └── services/         # ESPN data, odds helpers, archive, Elo sync, Monte Carlo, owner auth
├── frontend-v2/          # React 19 + Vite + Tailwind SPA (live frontend, served from dist/)
├── frontend/             # Legacy vanilla-JS frontend (kept as fallback)
├── data/                 # Elo ratings, caches, backups
└── ARCHITECTURE.md       # Full mathematical derivation
```

---

## Running Tests

```bash
.venv/bin/python -m pytest test_math_engine.py test_pool_optimizer.py test_build_a_bot.py test_ko_detection.py -v
```
