# Architecture & Mathematical Pipeline

This document describes the full prediction pipeline used by WM 2026 Predictor — from raw bookmaker data to an optimal SRF Tippspiel tip — together with the archive system, bot strategies, and engineering decisions behind them.

---

## Pipeline Overview

```
Raw bookmaker odds (H2H + O/U 2.5)
       │
       ▼
 1. Margin removal          → true H/D/A probabilities
       │
       ▼
 2. Elo rating model        → form-adjusted win/draw/loss
       │
       ▼
 3. 70/30 Elo-odds blend    → blended H/D/A probabilities
       │
       ▼
 4. xG solver (L-BFGS-B)   → λ_home, λ_away
       │
       ▼
 5. Dixon-Coles correction  → adjusted score probability matrix
       │
       ▼
 6. K.O. inflation          → conditional extra-time weighted xG
       │
       ▼
 7. xP calculator           → expected SRF Tippspiel points per tip
       │
       ▼
 8. Pool optimiser          → optimal contrarian tip
```

---

## 1. Odds Ingestion & Margin Removal

### Consensus aggregation

Multiple bookmakers price the same match differently. Rather than using a single book, the system collects every available price and takes the **median implied probability** per outcome:

```
p_implied(i, k) = 1 / o(i, k)   for bookmaker k, outcome i

p_consensus(i) = median_k( p_implied(i, k) )
```

This is more robust than averaging, as it is resistant to outlier books with unusual pricing.

**Over/Under 2.5 market**: totals odds are fetched lazily, per match, only when a user opens the detail view. This conserves API quota — the bulk `/api/matches` call fetches only H2H odds across all fixtures.

### Margin removal

Bookmakers embed an overround (`Σ p_implied > 1`) to guarantee profit. We remove it via **proportional normalisation**:

```
p_true(i) = p_consensus(i) / Σ p_consensus(j)
```

For the two-way O/U 2.5 market:

```
p_over25_true = p_over25_implied / (p_over25_implied + p_under25_implied)
```

---

## 2. Elo Rating System

Elo ratings track team strength dynamically across the tournament.

### Win probability

```
E_A = 1 / (1 + 10^((R_B − R_A) / 400))
```

### Rating update

After a match with outcome S_A (1 = win, 0.5 = draw, 0 = loss):

```
R_A_new = R_A + K × MoV × (S_A − E_A)
```

**K = 60** — higher than standard chess (32) to allow rapid adjustment across a short tournament (64 matches over ~4 weeks).

**Margin-of-victory multiplier** (MoV) — prevents blowouts from dominating the update:

| Goal difference | Multiplier |
|---|---|
| 1 | 1.000 |
| 2 | 1.500 |
| 3 | 1.750 |
| 4 | 1.875 |
| n > 3 | 1.750 + (n − 3) × 0.125 |

### Host nation bonus

USA, Canada, and Mexico receive a **+80 Elo bonus** applied during post-match updates to accurately evaluate host performance relative to expectations.

**This bonus is deliberately excluded from pre-match predictions.** Bookmaker odds already fully price in home advantage; adding it again would double-count and inflate home win probabilities.

### Elo history & idempotency

Every Elo update is logged to the MongoDB database along with a timestamp and match ID. The processed match IDs are tracked implicitly via the MongoDB `archive` collection and its `post_match_result.status` field — each result is applied exactly once regardless of how many times sync is triggered.

---

## 3. Elo–Odds Blending

Neither Elo alone nor raw bookmaker odds alone are optimal. Elo captures recent form and tournament trajectory; odds aggregate market wisdom, squad news, and injury information.

### Why restrict to the win/loss pool

Elo has no concept of draws. If you naively blend Elo and odds on the full H/D/A distribution, the draw probability gets deflated whenever Elo and odds disagree on home vs away strength. The fix is to restrict the blend to the **win/loss pool** and hold the draw probability constant.

### Blend

**Step 1** — extract win-share probabilities (draw excluded):

```
p_win_odds = p_home_true / (p_home_true + p_away_true)
p_win_elo  = E_A / (E_A + (1 − E_A − p_draw_true))
```

**Step 2** — 70 % market / 30 % Elo blend:

```
p_win_blended = 0.70 × p_win_odds + 0.30 × p_win_elo
```

**Step 3** — rescale back to full H/D/A:

```
p_home_final = p_win_blended × (p_home_true + p_away_true)
p_away_final = (1 − p_win_blended) × (p_home_true + p_away_true)
p_draw_final = p_draw_true    ← held constant
```

This guarantees `p_home + p_draw + p_away = 1` with no draw deflation.

---

## 4. xG Extraction (Poisson Solver)

Given the blended H/D/A probabilities and the O/U 2.5 probability, we reverse-engineer the Expected Goals (λ_home, λ_away) that best reproduce those market prices under a Poisson model.

### Score probability

```
P(i goals, j goals) = Poisson(i; λ_home) × Poisson(j; λ_away) × τ(i, j)
```

where τ is the Dixon-Coles correction (§5).

### Derived market probabilities

```
P_home_win = Σ_{i > j} P(i, j)
P_draw     = Σ_{i = j} P(i, j)
P_away_win = Σ_{i < j} P(i, j)
P_over25   = Σ_{i + j > 2} P(i, j)
```

### Objective function

SciPy L-BFGS-B minimises the weighted sum of squared errors:

```
loss = (P_home_win − p_home_final)²
     + (P_draw     − p_draw_final)²
     + (P_away_win − p_away_final)²
     + 2.0 × (P_over25 − p_over25_true)²    ← when O/U data is available
```

The `w_ou = 2.0` weight gives extra pull to the over/under constraint because it carries goal-total information that H2H alone cannot determine.

Bounds: `λ_home, λ_away ∈ [0.1, 5.0]`.

### Fallback chain

1. Solver with default initial guess `[1.2, 1.0]`
2. Retry with `[p_home × 3.5, p_away × 3.5]` if step 1 fails
3. Heuristic if both fail: `λ = max(0.1, min(5.0, 1.35 × (p / 0.45)))`

---

## 5. Dixon-Coles Score Matrix

The independent bivariate Poisson distribution systematically underestimates draws and 1-0/0-1 scorelines in football. Dixon & Coles (1997) correct the four low-scoring cells with a τ function:

```
τ(i, j) =
  1 − λ_home × λ_away × ρ    if i = 0, j = 0   (0-0 scoreline)
  1 + λ_home × ρ              if i = 0, j = 1   (0-1)
  1 + λ_away × ρ              if i = 1, j = 0   (1-0)
  1 − ρ                       if i = 1, j = 1   (1-1)
  1                           otherwise
```

**ρ = −0.15** — standard literature value for international football. Negative ρ upweights 0-0 and 1-1, downweights 1-0 and 0-1.

The full matrix covers **0–9 goals per team (100 cells)**. Truncation at 9 captures >99.9 % of probability mass. After applying τ, the matrix is renormalised to sum to 1.

---

## 6. K.O. Phase Adjustment

In knockout matches, a draw after 90 minutes leads to extra time (30 min). A naive approach — multiplying both λ values by 1.33 — overcounts because it assumes every match goes to extra time.

The correct adjustment weights the extra-time inflation by the probability that extra time is actually needed:

```
p_draw_90 = Σ_i P(i, i)         ← sum of the main diagonal of the 90-min matrix

et_factor = 1 + p_draw_90 / 3   ← 30 min ≈ ⅓ of a 90-min match

λ_home_ko = λ_home × et_factor
λ_away_ko = λ_away × et_factor
```

A match with 30 % draw probability gets a factor of `1.10`; a one-sided match with 15 % draw probability gets `1.05`. The resulting score matrix represents the probability of each scoreline **after 120 minutes (extra time included, penalties excluded)**, consistent with SRF Tippspiel rules.

---

## 7. Expected Points (xP) Calculation

For every possible tip `(g_home, g_away)` from 0:0 to 5:5 (36 tips) we compute expected SRF Tippspiel points:

```
xP(tip) = Σ_{i=0}^{9} Σ_{j=0}^{9} P(i, j) × pts(tip, actual=(i,j))
```

`pts(tip, actual)` implements the exact SRF scoring rules:

| Condition | Group stage | K.O. phase |
|---|---|---|
| Correct tendency (home/draw/away) | 5 | 10 |
| Correct home goals | +1 | +2 |
| Correct away goals | +1 | +2 |
| Correct goal difference | +3 | +6 |
| **All correct (exact score)** | **10** | **20** |

Goal difference bonus requires correct tendency. K.O. doubles all values.

---

## 8. Pool-Winning Strategy

Maximising xP is optimal in isolation. In a competitive pool, it fails: when everyone picks the same chalk tip, you share points with the field.

### Objective

Model the field as tipping the maximum-xP score ("chalk"). Your **advantage** when you tip score t:

```
A(t) = pts(t, actual) − pts(chalk, actual)
```

This is a random variable over actual outcomes. Compute:

```
E[A(t)]  = Σ_{i,j} P(i,j) × [pts(t,(i,j)) − pts(chalk,(i,j))]
SD[A(t)] = √( Σ_{i,j} P(i,j) × [pts(t,(i,j)) − pts(chalk,(i,j)) − E[A(t)]]² )
```

### Pool optimiser score

```
pool_score(t) = E[A(t)] + λ × SD[A(t)]
```

| λ | Strategy | When to use |
|---|---|---|
| 0.0 | Chalk — same as xP maximiser | Small pool; you are leading |
| 0.2–0.3 | Soft contrarian — different exact score, same tendency | Mild deficit; medium pool |
| 0.4–0.6 | Contrarian — may pick different tendency | Behind in pool; late group stage |
| ≥ 0.8 | Aggressive — draw gambles; high variance | Significant deficit; K.O. phase |

The top-5 tips ranked by `pool_score` are returned to the user.

---

## Bot Strategies

Five autonomous agents tip every match independently, each representing a fixed strategy. Their cumulative scores are tracked and visualised against the user.

| Bot | Logic |
|---|---|
| **Broker** | Pure bookmaker odds. Solves xG from H2H + O/U 2.5 consensus prices, ranks all tips by xP, picks the top. |
| **Professor** | Pure Elo. Derives H/D/A from Elo ratings (no odds input), solves for xG, picks top xP tip. Most likely to deviate from the market when Elo diverges. |
| **Rebel** | Scans all 36 tips and picks the tip with the highest xP that represents the underdog winning. Takes on risk when value is there. |
| **X-Sniper** | Picks the draw tip with the highest xP score — always a draw, never a home/away win. Profits when market underestimates draw probability. |
| **Gambler** | Samples from the top-10 xP tips using xP as a probability weight. Seeded by a hash of the match ID so the pick is deterministic and reproducible. |

---

## Retroactive Reconstruction

For matches played before the app started tracking (no pre-match odds snapshot exists), the system reconstructs the algo tip from the Elo state at match time:

1. Look up both teams' Elo ratings in the database immediately before the match timestamp
2. Apply host bonus (+80) where applicable
3. Derive H/D/A probabilities from Elo using a heuristic draw rate: `max(0.18, 0.28 − |ΔElo| / 10000)`
4. Solve for xG from those probabilities
5. Generate the score matrix and pick the top-xP tip

Reconstructed entries are flagged `algo_reconstructed: true` in the archive and displayed as `ALGO*` in the UI with a tooltip explaining the estimation.

---

## Prediction Archive Schema

The MongoDB `archive` collection stores documents keyed by `_id` (match ID) and tracks the full lifecycle of every prediction:

```json
{
  "<match_id>": {
    "metadata": {
      "home_team": "string",
      "away_team": "string",
      "home_disp": "🇩🇪 Germany",
      "away_disp": "🇧🇷 Brazil",
      "is_ko_phase": false
    },
    "pre_match_snapshot": {
      "timestamp_recorded": "ISO 8601",
      "odds": {
        "home": 2.10, "draw": 3.40, "away": 3.60,
        "over25": 1.75, "under25": 2.05
      },
      "elo_state": { "home_rating": 2010.0, "away_rating": 2140.0 }
    },
    "prediction": {
      "top_tip": "1:2",
      "user_tip": "1:1",
      "max_xp": 5.83,
      "algo_reconstructed": false,
      "bots": {
        "broker":    { "tip": "1:2" },
        "professor": { "tip": "0:2" },
        "rebel":     { "tip": "0:3" },
        "sniper":    { "tip": "1:1" },
        "gambler":   { "tip": "1:2" }
      }
    },
    "post_match_result": {
      "status": "completed",
      "actual_score": "1:1",
      "points_earned": 10,
      "algo_points": 0,
      "bot_points": {
        "broker": 0, "professor": 0, "rebel": 0, "sniper": 10, "gambler": 0
      }
    }
  }
}
```

---

## Design Decisions

| Decision | Rationale |
|---|---|
| Median consensus odds | More robust than first-found bookmaker; resistant to outlier pricing |
| Restricted 70/30 blend (win/loss pool only) | Prevents draw probability deflation — Elo has no draw concept |
| ρ = −0.15 for Dixon-Coles | Standard literature value for international football |
| K = 60 for Elo | Faster adaptation during a short tournament; typical WC values are 40–60 |
| Conditional K.O. extra-time factor | Avoids over-inflating goals in one-sided matches where extra time is unlikely |
| 0–9 goal matrix (100 cells) | Captures >99.9 % of probability mass; consistent between solver and display |
| λ on `E[A] + λ · SD[A]` | Classic mean-variance tradeoff from portfolio theory, applied to prediction pools |
| Lazy O/U 2.5 fetch | Totals data fetched per-match on detail view open; saves bulk API quota on the fixture list |
| Host bonus excluded from pre-match predictions | Bookmaker odds already price home advantage; adding Elo bonus would double-count it |
| Heuristic draw rate in reconstruction | No historical odds exist; `max(0.18, 0.28 − |ΔElo|/10000)` approximates draw likelihood from Elo gap |
| MongoDB idempotency guard | Elo updates are irreversible; re-processing the same match would compound rating changes |
