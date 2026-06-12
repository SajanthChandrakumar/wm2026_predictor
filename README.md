# WM 2026 Predictor

A quantitative prediction engine and analytics dashboard built for the **SRF Tippspiel** during the FIFA World Cup 2026. It reverse-engineers bookmaker odds to derive Expected Goals, applies a Dixon-Coles–corrected Poisson model, and calculates the mathematically optimal tip to maximise points in a closed prediction pool.

> **See [ARCHITECTURE.md](ARCHITECTURE.md) for a full explanation of the mathematics.**

---

## ⚠️ Disclaimer

This project is developed **strictly for scientific, educational, and research purposes** as a companion tool for the [SRF Tippspiel](https://wmtippspiel.srf.ch) — a free, non-monetary prediction game. It is not a gambling tool, betting advisory service, or financial product of any kind.

- The author **accepts no responsibility or liability** for any decisions made by third parties based on the output of this software.
- This tool does **not** constitute financial, investment, or betting advice.
- Using this software to place real-money wagers is entirely at the user's own risk and is explicitly **not** the intended use case.
- All probability estimates are model outputs subject to uncertainty and should never be treated as guaranteed outcomes.

By using this software you agree that the author cannot be held liable for any losses, damages, or legal consequences arising from its use.

---

## Features

| | |
|---|---|
| **Odds ingestion** | Live H2H + Over/Under 2.5 odds via The Odds API; margin-removed using proportional normalisation; consensus median across all bookmakers |
| **Elo ratings** | Dynamic Elo system for all 48 nations; K=60 with margin-of-victory multiplier; host nation bonus (+80) for USA, Canada, Mexico |
| **xG solver** | SciPy L-BFGS-B minimiser reverse-engineers Expected Goals from odds probabilities; Dixon-Coles corrected (ρ = −0.15) |
| **Score matrix** | Full bivariate Poisson probability matrix (0–9 goals); Dixon-Coles low-score correction applied |
| **xP calculator** | Simulates every possible tip against the score matrix using the exact SRF Tippspiel ruleset (5/1/1/3 pts, ×2 in K.O.) |
| **Pool strategy** | Contrarian mode maximises E[advantage vs field] + λ·σ[advantage] instead of raw xP — designed to finish #1 in a pool, not just average well |
| **K.O. phase** | Extra-time xG inflation is weighted by P(draw after 90 min), not a flat multiplier |
| **Auto Elo sync** | Idempotent background job (APScheduler, 04:00 daily) updates ratings from completed match scores |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Math | NumPy, SciPy (`optimize`, `stats`), Pandas |
| Frontend | Vanilla HTML/CSS/JS — no framework |
| Data | [The Odds API](https://the-odds-api.com) |

---

## Quick Start

```bash
# 1. Clone and enter the project
git clone https://github.com/SajanthChandrakumar/wm2026_predictor.git
cd wm2026_predictor

# 2. Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Set your API key
echo "ODDS_API_KEY=your_key_here" > .env

# 4. Start the server
uvicorn src.api:app --reload
```

Open **http://127.0.0.1:8000** in your browser.

---

## Tournament Operations

The system is designed to stay current throughout the tournament without manual intervention:

- **Automatic**: The Elo sync job runs daily at 04:00 and processes any completed matches from the last 72 hours.
- **Manual**: Press **Sync Elo Ratings** in the dashboard at any time to trigger an immediate update.
- **Idempotent**: `data/processed_matches.json` tracks processed match IDs — each result is applied exactly once regardless of how many times you sync.
- **Cache**: Match odds are cached for 1 hour in `data/matches_cache.json`. Use **Refresh Data** to force a live fetch (costs one API call).

---

## Project Structure

```
wm2026_predictor/
├── src/
│   ├── api.py            # FastAPI app, endpoints, orchestration
│   ├── math_engine.py    # All prediction mathematics
│   └── odds_engine.py    # The Odds API client
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── data/
│   ├── elo_ratings.csv   # Live Elo ratings for all 48 teams
│   ├── matches_cache.json
│   └── processed_matches.json
├── test_math_engine.py
├── test_api.py
├── ARCHITECTURE.md       # Full mathematical documentation
└── README.md
```

---

## Running Tests

```bash
.venv/bin/python -m pytest test_math_engine.py test_api.py -v
```
