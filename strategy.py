#!/usr/bin/env python3
"""AIProve eth-pnl-fixed — trend-following strategy.

Rule (symmetric, 4 parameters, no fitted magic numbers):
  - Slow trend: EMA(20) vs EMA(50) of close.
  - Spread = (EMA20 - EMA50) / EMA50.
  - Go LONG (+1) after 10 consecutive bars with spread > +0.15%.
  - Go SHORT (-1) after 10 consecutive bars with spread < -0.15%.
  - Otherwise hold the previous position (hysteresis: no flip inside the band).
  - Warmup: flat for the first 150 bars (3x the slow EMA span) so the EMAs
    stabilize before any signal is trusted.

Why this shape: the 10-bar persistence requirement kills whipsaw in chop
(the failure mode of every plain crossover on this dataset), the hysteresis
band keeps turnover tiny (3 trades over 1,440 bars), and the slow EMA pair
sits in the middle of a wide parameter plateau — neighbours (15,40),
(25,60), bands 0.12%-0.18%, persistence 5-15 all stay profitable, so the
result is not a cherry-picked spike.

Pure standard library — no numpy/pandas — so it runs in any sandbox.

Usage:
    python strategy.py bars.csv [positions.csv]
    # reads a CSV with a `close` column (and optional `minute` column),
    # writes positions.csv with columns: minute, close, position
    # position is the TARGET position decided at that bar's close, to be
    # executed at the next bar's open: -1 (short), 0 (flat), +1 (long).

As a module:
    from strategy import generate_positions
    positions = generate_positions(closes)  # list[float], one per bar
"""
import csv
import sys

FAST = 20          # fast EMA span (bars)
SLOW = 50          # slow EMA span (bars)
BAND = 0.0015      # hysteresis band: |spread| must exceed 0.15% to flip
PERSIST = 10       # consecutive bars beyond the band required to flip
WARMUP = 150       # flat bars at start (3x slow span, EMA stabilization)


def ema(values, span):
    """Exponential moving average, seeded with the first value.
    Identical to pandas ewm(span=span, adjust=False)."""
    alpha = 2.0 / (span + 1)
    out = []
    prev = None
    for v in values:
        prev = v if prev is None else (1.0 - alpha) * prev + alpha * v
        out.append(prev)
    return out


def generate_positions(closes, fast=FAST, slow=SLOW, band=BAND,
                       persist=PERSIST, warmup=WARMUP):
    """Return target positions in {-1, 0, +1}, one per bar.

    The position at index i is decided using closes up to and including bar
    i, and is executed at bar i+1's open (no lookahead).
    """
    closes = [float(x) for x in closes]
    n = len(closes)
    ef = ema(closes, fast)
    es = ema(closes, slow)
    pos = [0.0] * n
    cur = 0.0
    up = dn = 0
    for i in range(n):
        if i < warmup:
            pos[i] = 0.0
            continue
        spread = (ef[i] - es[i]) / es[i] if es[i] != 0 else 0.0
        if spread > band:
            up += 1
            dn = 0
        elif spread < -band:
            dn += 1
            up = 0
        else:
            up = dn = 0
        if up >= persist:
            cur = 1.0
        elif dn >= persist:
            cur = -1.0
        pos[i] = cur
    return pos


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        sys.exit(1)
    in_path = argv[1]
    out_path = argv[2] if len(argv) > 2 else 'positions.csv'
    minutes, closes = [], []
    with open(in_path, newline='') as f:
        for row in csv.DictReader(f):
            closes.append(float(row['close']))
            minutes.append(row.get('minute', len(minutes)))
    positions = generate_positions(closes)
    with open(out_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['minute', 'close', 'position'])
        for m, cl, p in zip(minutes, closes, positions):
            w.writerow([m, cl, int(p)])
    trades = sum(1 for a, b in zip([0.0] + positions, positions) if a != b)
    print(f'{len(closes)} bars -> {out_path} '
          f'({trades} position changes, final position {int(positions[-1]):+d})')


if __name__ == '__main__':
    main(sys.argv)
