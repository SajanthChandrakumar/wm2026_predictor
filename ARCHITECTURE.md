# Architecture & Mathematical Pipeline

This document describes the full prediction pipeline used by WM 2026 Predictor, from raw bookmaker data to an optimal tip for the SRF Tippspiel.

---

## Overview

```
Raw bookmaker odds
       │
       ▼
 1. Margin removal          → true probabilities
       │
       ▼
 2. Elo rating model        → form-adjusted win/draw/loss
       │
       ▼
 3. 70/30 Elo-odds blend    → blended H/D/A probabilities
       │
       ▼
 4. xG solver (Poisson)     → λ_home, λ_away
       │
       ▼
 5. Dixon-Coles correction  → adjusted score matrix
       │
       ▼
 6. K.O. inflation          → extra-time weighted xG
       │
       ▼
 7. xP calculator           → expected SRF Tippspiel points per tip
       │
       ▼
 8. Pool strategy           → optimal contrarian tip
```

---

## 1. Margin Removal

Bookmakers embed a margin (overround) in their odds to guarantee profit. Before any probability work, this margin must be stripped.

**Implied probability** from decimal odds `o`:

```
p_implied = 1 / o
```

The sum `Σ p_implied` over a market (home + draw + away) exceeds 1.0 by the margin. We remove it via **proportional normalisation**:

```
p_true(i) = p_implied(i) / Σ p_implied(j)
```

This preserves the relative shape of the probability distribution while making the three outcomes sum to exactly 1.

**Consensus across bookmakers**: rather than taking a single book, we collect all available prices and take the **median implied probability** per outcome before applying margin removal. This makes the signal more robust against outlier books with unusual pricing.

**Over/Under 2.5 market**: this is a two-way market, so the correction is:

```
p_over25_true = p_over25_implied / (p_over25_implied + p_under25_implied)
```

---

## 2. Elo Rating System

Elo ratings track team strength dynamically. Each team starts with a baseline rating and is updated after every completed match.

**Win probability** for team A vs team B:

```
E_A = 1 / (1 + 10^((R_B - R_A) / 400))
```

**Rating update** after a match with outcome S_A (1 = win, 0.5 = draw, 0 = loss):

```
R_A_new = R_A + K × MoV × (S_A − E_A)
```

Where:
- **K = 60** — higher than standard chess (32) to allow faster adjustment during a short tournament
- **MoV** — margin-of-victory multiplier to prevent blowouts from being over-weighted:

| Goal difference | Multiplier |
|---|---|
| 1 | 1.00 |
| 2 | 1.50 |
| 3 | 1.75 |
| 4 | 1.875 |
| +n beyond 3 | +0.125 per extra goal |

**Host nation advantage**: USA, Canada, and Mexico receive a **+80 Elo bonus** in all their matches. This is applied before computing `E_A`, not baked into the stored rating, so it only affects predictions and not the post-match rating update.

---

## 3. Elo–Odds Blending

Neither Elo alone nor raw bookmaker odds alone are optimal. Elo captures recent form; odds aggregate market wisdom and squad news.

We blend in a **70/30 split restricted to the win/loss pool**. This is the critical detail: draws are handled separately to avoid deflation.

**Step 1 — extract win/loss pool probabilities:**

```
p_win_odds  = p_home_true / (p_home_true + p_away_true)
p_win_elo   = E_A / (E_A + (1 − E_A − p_draw_true))
```

**Step 2 — blend in win/loss space:**

```
p_win_blended = 0.70 × p_win_odds + 0.30 × p_win_elo
```

**Step 3 — rescale back to H/D/A:**

```
p_home_final = p_win_blended × (p_home_true + p_away_true)
p_away_final = (1 − p_win_blended) × (p_home_true + p_away_true)
p_draw_final = p_draw_true          ← unchanged
```

This ensures `p_home + p_draw + p_away = 1` and that Elo can shift credit between home/away without touching the draw probability.

---

## 4. xG Extraction (Poisson Solver)

Given the blended H/D/A probabilities and (optionally) the Over 2.5 market probability, we reverse-engineer the Expected Goals (λ_home, λ_away) that best explain those market prices.

**Poisson score probability:**

```
P(home = i, away = j) = Poisson(i; λ_home) × Poisson(j; λ_away)
                       × τ_correction(i, j)
```

where τ is the Dixon-Coles correction (see §5).

**Derived market probabilities** from a score matrix:

```
P_home_win = Σ_{i>j} P(i, j)
P_draw     = Σ_{i=j} P(i, j)
P_away_win = Σ_{i<j} P(i, j)
P_over25   = Σ_{i+j>2} P(i, j)
```

**Objective function** (SSE minimised by SciPy L-BFGS-B):

```
loss = (P_home_win − p_home_final)²
     + (P_draw     − p_draw_final)²
     + (P_away_win − p_away_final)²
     + w_ou × (P_over25 − p_over25_true)²
```

where `w_ou = 2.0` gives extra weight to the Over/Under constraint when available. If no over/under data exists, that term is dropped.

**Robustness**: if the solver does not converge (`result.success = False`), it retries with a different initial guess (`[p_home × 3.5, p_away × 3.5]`). If it still fails, a heuristic fallback is used:

```
λ_home = max(0.1, min(5.0, 1.35 × (p_home / 0.45)))
λ_away = max(0.1, min(5.0, 1.35 × (p_away / 0.45)))
```

---

## 5. Dixon-Coles Score Matrix

The bivariate Poisson distribution slightly underestimates draws and 1-0/0-1 scorelines. The Dixon-Coles (1997) τ correction adjusts the four low-score cells:

```
τ(i, j) =
  1 − λ_home × λ_away × ρ    if i = 0, j = 0
  1 + λ_home × ρ              if i = 0, j = 1
  1 + λ_away × ρ              if i = 1, j = 0
  1 − ρ                       if i = 1, j = 1
  1                           otherwise
```

We use **ρ = −0.15**, which upweights 0-0 and 1-1 scorelines and downweights 1-0 and 0-1. The matrix is then renormalised to sum to 1.

The full score matrix covers **0–9 goals** per team (100 cells). Truncation at 9 goals captures >99.9% of probability mass.

---

## 6. K.O. Phase Adjustment

In K.O. matches, draws after 90 minutes lead to extra time (and potentially penalties). This inflates the expected number of goals scored relative to the same xG in a group match.

The conventional approach (multiply λ by 1.33) is naive because it ignores that extra time only occurs when the game is actually drawn at 90 minutes. We weight the inflation by the probability that extra time is needed:

```
p_draw_90 = Σ_{i} P(i, i)        ← sum of diagonal of 90-min matrix

et_factor = 1 + p_draw_90 / 3

λ_home_ko = λ_home × et_factor
λ_away_ko = λ_away × et_factor
```

The `/3` arises from approximately 30 extra minutes ≈ ⅓ of 90 minutes. The result: a match with a high draw probability (e.g., 0.30) gets a factor of `1 + 0.30/3 = 1.10`, while a match with a low draw probability (0.15) gets `1.05`. This is more accurate than a blanket 1.33×.

The score matrix for a K.O. match represents the probability of each scoreline **after 120 minutes, excluding penalties** — consistent with the SRF Tippspiel rules.

---

## 7. Expected Points (xP) Calculation

For every possible tip `(g_home, g_away)` we compute the expected SRF Tippspiel points by summing over all possible actual scores:

```
xP(tip) = Σ_{i,j} P(i, j) × pts(tip, actual=(i,j))
```

where `pts(tip, actual)` implements the exact SRF scoring rules:

| Condition | Group pts | K.O. pts |
|---|---|---|
| Correct tendency (home/draw/away) | 5 | 10 |
| Correct home goals | +1 | +2 |
| Correct away goals | +1 | +2 |
| Correct goal difference | +3 | +6 |
| **All correct (exact score)** | **10** | **20** |

The optimal **safe tip** is the `(g_home, g_away)` that maximises `xP`.

---

## 8. Pool-Winning Strategy

Maximising xP is the right strategy if you are playing alone. In a competitive pool, however, maximising your absolute points is not sufficient — you need to **outscore the field**. This requires a contrarian approach.

**Model of the field**: we assume most participants ("chalk" players) tip the maximum-xP score. Their expected points for a given match is therefore `xP_chalk = max xP`.

**Your advantage** when you tip score `t`:

```
A(t) = your_points(t) − chalk_points
```

This is a random variable. We compute:

```
E[A(t)]  = Σ_{i,j} P(i,j) × [pts(t, (i,j)) − pts(chalk, (i,j))]
SD[A(t)] = √( Σ_{i,j} P(i,j) × [pts(t,(i,j)) − pts(chalk,(i,j)) − E[A(t)]]² )
```

**Objective** — the pool strategy tip maximises:

```
score(t) = E[A(t)] + λ × SD[A(t)]
```

where **λ (aggressiveness)** is the user-controlled parameter (0 – 1.5). At λ = 0 you get the chalk tip. As λ increases, the optimizer increasingly favours tips with higher variance — tips that are wrong more often but score big when they land. This is the correct strategy when you are behind in a pool and need to make up ground.

The top-5 tips are returned, ranked by this score, so the user can choose their own risk level.

---

## Design Decisions

| Decision | Rationale |
|---|---|
| Median consensus odds | More robust than first-found bookmaker; resistant to outlier pricing |
| Restricted Elo-odds blend (win/loss pool only) | Prevents draw probability deflation from Elo, which has no draw concept |
| ρ = −0.15 for Dixon-Coles | Standard literature value for international football |
| K = 60 for Elo | Faster adaptation during a short tournament; standard value for WC is 40–60 |
| Conditional K.O. extra-time factor | Avoids over-inflating goals in one-sided K.O. matches where draws are rare |
| 0–9 goal matrix (max_goals = 10) | Captures >99.9% of probability; consistent between solver and display |
| Aggressiveness λ on E[A] + λ·SD[A] | Classic mean-variance tradeoff from portfolio theory, applied to prediction pools |
