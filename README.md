# WM 2026 Predictor

<div align="center">

**A quantitative prediction engine and analytics dashboard for the FIFA World Cup 2026**

[![Python](https://img.shields.io/badge/Python-3.12+-3776ab?style=flat&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat)]()

[Features](#features) • [Quick Start](#quick-start) • [Architecture](#architecture) • [Views](#views) • [Disclaimer](#disclaimer)

</div>

---

## Overview

**WM 2026 Predictor** is a sophisticated statistical prediction engine built for the [SRF Tippspiel](https://wmtippspiel.srf.ch) — a free, non-monetary prediction competition during the FIFA World Cup 2026.

The system combines:
- **Real-time bookmaker odds analysis** (consensus across all major sportsbooks)
- **Dynamic Elo rating system** (updated daily from completed match results)
- **Expected Goals (xG) solver** (reverse-engineered from odds using Dixon-Coles correction)
- **Bivariate Poisson modeling** (full probability matrix for match outcomes)
- **Strategic tip optimization** (contrarian pool strategy to maximize winning position)

All predictions are calculated with full transparency and mathematical rigor. The interactive dashboard provides match predictions, performance tracking, and head-to-head comparison between your manual tips and the algorithm.

> **See [ARCHITECTURE.md](ARCHITECTURE.md) for the complete mathematical documentation.**

---

## Disclaimer

This project is developed **strictly for scientific, educational, and research purposes** as a companion tool for the [SRF Tippspiel](https://wmtippspiel.srf.ch) — a free, non-monetary prediction competition.

- The author **accepts no responsibility or liability** for any decisions made by third parties based on the output of this software.
- This tool does **not** constitute financial, investment, or betting advice.
- Using this software to place real-money wagers is entirely at the user's own risk and is explicitly **not** the intended use case.
- All probability estimates are model outputs subject to uncertainty and should never be treated as guaranteed outcomes.

By using this software you agree that the author cannot be held liable for any losses, damages, or legal consequences arising from its use.

---

## Features

| Feature | Description |
|---------|-------------|
| **Live Odds Ingestion** | Real-time H2H + Over/Under 2.5 odds via The Odds API; margin-removed using proportional normalisation; consensus median across all bookmakers |
| **Dynamic Elo Ratings** | Elo system for all 48 nations; K=60 with margin-of-victory multiplier; host nation bonus (+80) for USA, Canada, Mexico applied exclusively to post-match updates |
| **xG Solver** | SciPy L-BFGS-B minimiser reverse-engineers Expected Goals from odds probabilities; Dixon-Coles corrected (ρ = −0.15) |
| **Score Matrix** | Full bivariate Poisson probability matrix (0–9 goals); Dixon-Coles low-score correction applied |
| **xP Calculator** | Simulates every possible tip against the score matrix using the exact SRF Tippspiel ruleset (5/1/1/3 pts, ×2 in K.O.) |
| **Pool Strategy** | Contrarian mode maximises E[advantage vs field] + λ·σ[advantage] instead of raw xP — designed to finish #1 in a pool, not just average well |
| **K.O. Phase Handling** | Extra-time xG inflation is weighted by P(draw after 90 min), not a flat multiplier |
| **Auto Elo Sync** | Idempotent background job (APScheduler, 04:00 daily) updates ratings from completed match scores |
| **Performance Dashboard** | Tracks completed matches, total SRF points, hit rate, and tendency accuracy; retroactively populates entries for matches played before app startup |
| **You vs Algo** | Head-to-head comparison between your manual tips and the algorithm's predictions with points and accuracy side-by-side |
| **Inline Tip Editor** | Enter or correct your SRF tip directly in the Performance view; points recalculated immediately on save |
| **Algo Tip Reconstruction** | For pre-app matches without live odds, algo tips are reconstructed from pre-match Elo baselines and flagged as `ALGO*` |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12, FastAPI, Uvicorn, APScheduler |
| **Mathematics** | NumPy, SciPy (`optimize`, `stats`), Pandas |
| **Frontend** | Vanilla HTML/CSS/JavaScript — no framework; dark navy + gold WC palette |
| **Data Sources** | [The Odds API](https://the-odds-api.com), API-Football (scores) |

---

## Quick Start

### Prerequisites
- Python 3.12+
- An API key from [The Odds API](https://the-odds-api.com)

### Installation

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
uvicorn src.main:app --reload
```

Open **http://127.0.0.1:8000** in your browser.

---

## Tournament Operations

The system is designed to stay current throughout the tournament without manual intervention:

- **Automatic**: The Elo sync job runs daily at 04:00 and processes any completed matches from the last 72 hours.
- **Manual**: Press **Sync Elo Ratings** in the dashboard at any time to trigger an immediate update.
- **Idempotent**: `data/processed_matches.json` tracks processed match IDs — each result is applied exactly once regardless of how many times you sync.
- **Cache**: Match odds are cached with dynamic TTL in `data/matches_cache.json`. Use **Refresh Data** to force a live fetch (costs one API call).

---

## Project Structure

```
wm2026_predictor/
├── src/
│   ├── api.py                   # FastAPI app, endpoints, orchestration
│   ├── math_engine.py           # All prediction mathematics
│   └── odds_engine.py           # The Odds API client
├── frontend/
│   ├── index.html               # Main dashboard UI
│   ├── style.css                # Professional styling (navy + gold theme)
│   └── app.js                   # Client-side interactivity
├── data/
│   ├── elo_ratings.csv          # Live Elo ratings for all 48 teams
│   ├── elo_history.json         # Per-match Elo snapshots
│   ├── prediction_archive.json  # Match results + user/algo tips + points
│   ├── matches_cache.json       # Cached odds with TTL
│   └── processed_matches.json    # Idempotency tracker
├── test_math_engine.py          # Unit tests for mathematics
├── test_api.py                  # Integration tests
├── ARCHITECTURE.md              # Full mathematical documentation
├── README.md                    # This file
└── requirements.txt             # Python dependencies
```

---

## Dashboard Views

The application provides five intuitive views accessible from the sidebar:

| View | Description |
|------|-------------|
| **Dashboard** | All tournament fixtures grouped by day; click any match for the full prediction breakdown including probability matrix, Elo comparison, and xP analysis |
| **Top Value Bets** | Fixtures ranked by Expected Points — highest xP tip first; identify the best-scoring opportunities according to the algorithm |
| **Model Edge** | Highlights where Elo ratings diverge most from bookmaker consensus — potential field advantages where the model finds value |
| **Team Form** | Interactive Elo rating trajectory per team across the tournament; track how each nation's strength evolves with results |
| **Performance** | Your SRF points total, hit rate (tendency accuracy), complete match history with inline tip editor, and You vs Algo head-to-head comparison |

---

## Architecture Highlights

- **`ensure_teams_exist(*teams)`** — the only place new Elo rows are created. Prevents hidden side-effects from CSV operations.
- **Elo ratings column is always `float64`** — enforced on CSV load to prevent silent type conversion issues.
- **Host-bonus (+80) applied only to post-match updates**, not to pre-match predictions (odds already price home advantage).
- **Prediction archive** stores `user_tip`, `top_tip` (algo), `points_earned`, and `algo_points` separately for full transparency.
- **Dynamic TTL cache**: >24h to kick-off → 12h cache; 2–24h → 1h; <2h → 15min.

For comprehensive technical details, see **[ARCHITECTURE.md](ARCHITECTURE.md)**.

---

## Running Tests

```bash
.venv/bin/python -m pytest test_math_engine.py test_api.py -v
```

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## Attribution

Built as a hobby and educational project exploring data science, software architecture, and probabilistic modeling for the 2026 FIFA World Cup.

---

## Haftungsausschluss (German Disclaimer)

Dieses Projekt ist ein reines Hobby- und Bildungsprojekt, das aus persönlichem Interesse an Data Science, Software-Architektur und Wahrscheinlichkeitsrechnung entwickelt wurde.

Die durch diese Software generierten Daten, Matrizen und Expected-Points-Berechnungen (xP) dienen ausschließlich zu Informations- und Analysezwecken. Sie stellen **ausdrücklich keine Anlage-, Finanz- oder Wettberatung dar**.

Der Autor übernimmt absolut keine Verantwortung oder Haftung für die Richtigkeit der Vorhersagen oder für jegliche finanzielle Verluste, die durch die direkte oder indirekte Nutzung dieses Repositories entstehen.

---

<div align="center">

Built for the FIFA World Cup 2026

</div>
