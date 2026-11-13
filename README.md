# eth-pnl-fixed — AIProve bounty entry (PREP ONLY, not submitted)

Bounty: `eth-pnl-fixed`, 2,000,000 PROVE, AutoGrade, closes **Nov 20, 2026 13:49 UTC**.
Metric: **net PnL after costs** (maker + taker fees, slippage scaled by size);
ties break on lower max drawdown. The sandbox replays the strategy on the
frozen 1,440-bar ETH/USDT 1-minute dataset **plus a held-out tail**, so the
strategy must be a general rule, not a fitted curve.

Challenge spec + data:
`https://github.com/AIProveRH/aiprove/tree/main/challenges/eth-backtest`
(real Binance ETH/USDT spot bars, 24h window ending 2026-11-13 12:17 UTC).

**Status: PREP ONLY — nothing submitted to aiprove.fun.** Repo submission
(repo @ commit + transcript) comes later.

## The strategy

Trend-following EMA crossover with hysteresis + persistence confirmation.
Symmetric (longs and shorts by the same rule), 4 parameters:

| Parameter | Value | Role |
| --- | --- | --- |
| Fast EMA | 20 bars | trend |
| Slow EMA | 50 bars | trend |
| Hysteresis band | 0.15% | `\|(EMA20-EMA50)/EMA50\|` must exceed it to flip |
| Persistence | 10 bars | spread must stay beyond the band 10 bars in a row |
| Warmup | 150 bars | flat while EMAs stabilize (3× slow span) |

Rules:

- Spread > +0.15% for 10 consecutive bars → **LONG (+1)**.
- Spread < −0.15% for 10 consecutive bars → **SHORT (−1)**.
- Otherwise **hold the previous position** (no flip inside the band).
- Position is the *target* decided at bar i's close, executed at bar i+1's
  open — no lookahead, no phantom fills.

The persistence requirement is the key idea: plain crossovers whipsaw in
chop (the always-in EMA(12,26) loses −9.3% net on this dataset, MACD
−33.8%). Requiring 10 confirming bars kills the chop trades while still
catching the real trend. Turnover is tiny: **3 trades over 1,440 bars**,
which is what makes the result survive punitive cost assumptions.

## Files

| File | What it is |
| --- | --- |
| `strategy.py` | The entry. Pure stdlib (no numpy/pandas), so it runs in any sandbox. `generate_positions(closes)` → positions in {−1, 0, +1}; CLI reads `bars.csv`, writes `positions.csv`. |
| `backtest.py` | Local backtest harness (numpy/pandas). Imports `strategy.py`, reports net PnL, halves, cost sensitivity. |
| `positions.csv` | Positions produced on the sample bars (reference output). |
| `research/` | The candidate sweeps (rounds 1–4) that selected this strategy. |
| `README.md` | This file. |

Run it:

```sh
python strategy.py /path/to/bars.csv positions.csv
python backtest.py /path/to/bars.csv            # 10 bps fee + 2 bps slip/side
python backtest.py /path/to/bars.csv 20 0       # 20 bps/side, no slippage
```

## Backtest results (base cost: 10 bps fee + 2 bps slippage per side)

Capital $10,000 notional, positions ±100% / flat.

| Metric | Value |
| --- | --- |
| **Net PnL** | **+$314.73 (+3.15%)** |
| Gross PnL | +$374.73 |
| Costs | $60.00 (3 trades, 5.0× turnover) |
| Max drawdown | −2.03% |
| Buy & hold (same window) | −3.36% |

Trade log:

| Bar | Price | Change |
| --- | --- | --- |
| 237 | 2012.87 | flat → long |
| 858 | 1998.67 | long → short |
| 1097 | 1936.95 | short → long (held to end, 1960.59) |

## Validation (anti-overfitting)

The dataset is one down day (−3.36%): a range-bound first half (−0.58%)
then a sharp selloff (−2.78%). A strategy that only wins on the full sample
is suspect, so it was validated on splits:

| Split | Net PnL | Buy & hold |
| --- | --- | --- |
| Half 1 (bars 0–719, chop) | −0.00% | −0.58% |
| Half 2 (bars 720–1439, trend) | +3.04% | −2.78% |
| Q1 / Q2 / Q3 / Q4 | −0.03% / −0.23% / +2.59% / +0.41% | −0.61% / −0.11% / −4.60% / +1.83% |

The profile is the right one for an unknown held-out tail: ~flat in chop,
profitable in trend, never deeply negative in any quarter.

**Parameter plateau, not a spike.** Neighbouring configurations all stay
profitable at base cost, so the result does not depend on one lucky
parameter set:

| Config (fast, slow, band, k) | Net % |
| --- | --- |
| (15,40,0.15%,5/10/15) | +2.74 / +1.31 / +1.76 |
| (20,50,0.12%,10/15) | +2.94 / +2.73 |
| **(20,50,0.15%,5/10/15)** | **+2.40 / +2.48 / +2.51** |
| (20,50,0.18%,5/10/15) | +0.55 / +1.54 / +1.87 |
| (25,60,0.15%,5/10/15) | +2.10 / +2.64 / +2.33 |
| (20,60,0.15%,10/15) | +3.71 / +2.82 |

The submitted (20,50,0.15%,10) is the **centre of the plateau** (the classic
20/50 pair, middle band, middle persistence) — deliberately *not* the
grid maximum (20,60,0.15%,10 at +3.71%), which would be cherry-picking.

**Cost sensitivity.** The grader's exact fee/slippage schedule is not
published, so the strategy was checked across a wide range (per side,
slippage 0):

| Cost/side | 5 bps | 12 bps | 20 bps | 30 bps | 50 bps | 75 bps |
| --- | --- | --- | --- | --- | --- | --- |
| Net PnL | +3.50% | +3.15% | +2.75% | +2.25% | +1.25% | −0.00% |

Positive up to ~50 bps/side — it survives even a very punitive cost model
because it trades only 3 times.

## What was rejected (and why)

- **Plain EMA crossovers / MACD / short momentum**: −5% to −45% net.
  Whipsaw in the choppy first half + fee bleed. High turnover is fatal at
  1-minute volatility (~10.8 bps/bar) with 12 bps/side costs.
- **RSI / Bollinger mean reversion**: wins the choppy half (+1.1%) but
  loses the trending half (−1.4% to −5.3%) — the wrong regime for the
  second half, and the held-out tail is unknowable.
- **Fast parameter sets with big headline numbers** (e.g. (9,21,0.20%,10)
  at +4.06%): neighbours swing to −1.6%/−3.1% — spikes, not plateaus.
  Rejected as overfit.

## Caveats

- The grader's exact cost model, capital base, and position-format
  expectations are not published; the backtest assumes $10,000 capital,
  ±100% positions, fills at the next bar's open, 10 bps fee + 2 bps
  slippage per side. The strategy's 3-trade profile makes the result
  insensitive to the cost assumption (see table above).
- The strategy ends the sample **long (+1)** after the late bounce. If the
  held-out tail resumes the downtrend, it flips short after the 10-bar
  confirmation delay (~10–30 minutes of adverse move). No end-of-sample
  flattening was added — that would be sample-specific hacking.
- `strategy.py` is dependency-free; `backtest.py` needs numpy/pandas
  (local tooling only, not part of the graded entry).
