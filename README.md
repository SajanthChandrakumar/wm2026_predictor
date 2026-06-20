# WM 2026 Predictor

A full-stack quantitative prediction engine built for the **FIFA World Cup 2026**, designed to maximise points in the [SRF Tippspiel](https://wmtippspiel.srf.ch) — a competitive closed prediction pool. The system reverse-engineers bookmaker odds into Expected Goals, applies a Dixon-Coles–corrected bivariate Poisson model, blends in a live Elo rating system, and computes the mathematically optimal tip for each match.

> See [ARCHITECTURE.md](ARCHITECTURE.md) for the full mathematical derivation.

---

## Motivation

In a closed prediction pool, **maximising raw expected points is the wrong objective**. If everyone picks the chalk tip, you share points with the field even when you're right. The correct strategy is to maximise your *advantage over the field* — which sometimes means taking a calculated contrarian position.

This system implements that distinction: a chalk mode (maximise expected points) and a pool mode (maximise `E[advantage] + λ · SD[advantage]`, where λ controls aggressiveness).

---

## ⚠️ Disclaimer

This project is developed strictly for **scientific, educational, and research purposes** as a companion tool for the SRF Tippspiel — a free, non-monetary prediction game. It is not a gambling tool, betting advisory service, or financial product of any kind. All probability estimates are model outputs subject to uncertainty and should not be treated as guaranteed outcomes. The author accepts no liability for decisions made based on this software.

---

## Technical Highlights

| Component | Detail |
|---|---|
| **Prediction model** | Dixon-Coles bivariate Poisson (ρ = −0.15); SciPy L-BFGS-B reverse-engineer solver for xG |
| **Odds ingestion** | The Odds API — consensus **median** across all bookmakers (H2H + O/U 2.5); proportional margin removal |
| **Elo system** | Dynamic ratings for all 48 nations; K = 60; margin-of-victory multiplier; +80 host bonus (USA/CAN/MEX) on post-match updates only |
| **Probability blend** | 70 % bookmaker odds / 30 % Elo, restricted to the win/loss pool — draw probability held fixed to prevent deflation |
| **K.O. phase** | Extra-time xG inflation weighted by P(draw after 90 min) — conditional, not a flat 1.33× multiplier |
| **xP optimiser** | Evaluates all 36 possible tips (0:0 – 5:5) against the full score matrix using the exact SRF Tippspiel scoring rules |
| **Pool strategy** | Contrarian objective: `E[advantage vs chalk] + λ · SD[advantage]`; λ = 0 reproduces chalk, λ ≈ 0.3 = soft contrarian, λ ≥ 0.5 = true draw gambles |
| **Bot strategies** | Five independent tipping agents: Broker (pure market), Professor (pure Elo), Rebel (best underdog), X-Sniper (highest-xP draw), Gambler (weighted-random, seeded by match ID) |
| **Caching** | Dynamic TTL: >24 h to kick-off → 12 h; 2–24 h → 1 h; <2 h → 15 min. Totals (O/U 2.5) fetched lazily per match to conserve API quota |
| **Elo sync** | Idempotent daily background job (APScheduler, 04:00 UTC); tracks processed match IDs; retroactively creates archive entries for pre-app matches |

---

## Dashboard Views

| View | Description |
|---|---|
| **Dashboard** | All tournament fixtures grouped by day with live probabilities, algo tips, and team form badges |
| **Top Value Bets** | Fixtures ranked by Expected Points — highest xP tip first |
| **Model Edge** | Where Elo diverges most from market consensus — visualised as paired probability bars |
| **Team Form** | Per-team Elo trajectory across the tournament (Chart.js line chart) |
| **Performance** | Full analytics: your SRF points, hit rate, You vs Algo head-to-head, bot scoreboard, cumulative points race, and editable match history |

---

## Performance & Tracking

The Performance view tracks three parallel scoring streams in real time:

- **You** — manual tips entered via the inline editor (or imported from the SRF site)
- **Algo** — the system's top-pick tip at the time of prediction; retroactively reconstructed from pre-match Elo baselines for matches played before the app started (flagged as `ALGO*`)
- **Bots** — five autonomous agents, each with a fixed strategy; scored independently against every completed result

The **You vs Algo** head-to-head panel shows total points, tendency hit rate, and a progress bar for each, with a live leader message.

The **bot scoreboard** ranks all five bots by total points, average per match, and tendency accuracy. A cumulative points race chart (Chart.js) visualises how each strategy has performed over the tournament.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/matches` | All fixtures with odds, Elo, top tip, xP, and model edge; `?force=true` bypasses cache |
| `POST` | `/api/predict` | Full prediction for one match: xG, score matrix, ranked tips; accepts K.O. / resting toggles |
| `GET` | `/api/archive` | Complete prediction archive: all matches, user tips, algo tips, bot tips, results, and points |
| `POST` | `/api/archive/user_tip` | Save or update a user tip; recalculates points if result is already known |
| `GET` | `/api/elo_history` | Per-team Elo snapshots across the tournament (powers Team Form chart) |
| `POST` | `/api/sync_elo` | Trigger an immediate Elo sync from completed match scores |
| `GET` | `/api/quota` | Remaining requests for The Odds API and API-Football |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn, APScheduler |
| Math | NumPy, SciPy (`optimize.minimize`, L-BFGS-B), Pandas |
| Frontend | Vanilla HTML/CSS/JS — zero framework, zero build step |
| Charts | Chart.js (team Elo trajectory, bot cumulative points race) |
| Data | The Odds API (live odds + match scores), API-Football (supplementary scores) |
| Design | Dark navy + gold WC palette; CSS custom properties; Spring easing animations; fully responsive; `prefers-reduced-motion` support |

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

# 3. API key
echo "ODDS_API_KEY=your_key_here" > .env

# 4. Start
uvicorn src.main:app --reload
```

Open **http://127.0.0.1:8000** in your browser.

---

## Tournament Operations

| Operation | How |
|---|---|
| **Auto Elo sync** | Runs daily at 04:00 UTC via APScheduler |
| **Manual sync** | Press **Sync Elo Ratings** in the sidebar |
| **Idempotency** | `data/processed_matches.json` tracks processed match IDs — each result is applied exactly once |
| **Cache control** | Dynamic TTL; press **Refresh Data** to force a live fetch (costs one API call) |
| **Scores cache** | Completed match scores are cached for 30 min — syncing twice within that window uses cached data |

---

## Project Structure

```
wm2026_predictor/
├── src/
│   ├── api.py               # FastAPI app, all endpoints, orchestration, bot computation
│   ├── math_engine.py       # Elo, xG solver, Dixon-Coles, xP, pool optimiser, Elo sync
│   └── odds_engine.py       # The Odds API client; quota tracking
├── frontend/
│   ├── index.html           # SPA shell (5 views + detail pane)
│   ├── style.css            # Design system: WC palette, animations, responsive layout
│   └── app.js               # View logic, Chart.js charts, API calls, inline tip editor
├── data/
│   ├── elo_ratings.csv          # Live Elo ratings for all 48 + reserve teams
│   ├── elo_history.json         # Per-match Elo snapshots (Team Form chart + reconstruction)
│   ├── prediction_archive.json  # All matches: pre-match snapshot, tips, results, points
│   ├── matches_cache.json       # Odds cache (dynamic TTL)
│   └── processed_matches.json   # Processed match IDs (idempotency guard)
├── test_math_engine.py
├── test_api.py
├── ARCHITECTURE.md          # Full mathematical derivation
└── README.md
```

---

## Running Tests

```bash
.venv/bin/python -m pytest test_math_engine.py test_api.py -v
```

---

## Haftungsausschluss

Dieses Projekt ist ein Hobby- und Bildungsprojekt, das aus persönlichem Interesse an Data Science, Software-Architektur und Wahrscheinlichkeitsrechnung entwickelt wurde. Die generierten Daten und Expected-Points-Berechnungen dienen ausschließlich zu Informations- und Analysezwecken und stellen ausdrücklich **keine Anlage-, Finanz- oder Wettberatung** dar. Der Autor übernimmt keine Haftung für Verluste, die durch die Nutzung dieser Software entstehen.
