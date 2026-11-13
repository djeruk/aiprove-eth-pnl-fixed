#!/usr/bin/env python3
"""Round 4: confirm the (20,50) plateau; warmup; cost sensitivity; trade log."""
import numpy as np
import pandas as pd
from sweep import load, backtest, ema
from sweep3 import hyst_persist

df = load()
c = df['close'].to_numpy()
n = len(df)
half = n // 2


def ev(f, s, band, k, warmup=0):
    pos = hyst_persist(f, s, band, k, warmup=warmup)
    full = backtest(c, pos)
    h1 = backtest(c[:half], pos[:half])
    h2 = backtest(c[half:], pos[half:])
    lo = backtest(c, pos, fee_bps=5, slip_bps=0)
    hi = backtest(c, pos, fee_bps=20, slip_bps=0)
    return pos, full, h1, h2, lo, hi


print('=== plateau neighborhood of (20,50,0.0015), k=10 ===')
for f, s, band in [(15, 40, 0.0015), (20, 50, 0.0012), (20, 50, 0.0015),
                   (20, 50, 0.0018), (25, 60, 0.0015), (20, 60, 0.0015),
                   (20, 50, 0.0015)]:
    for k in [5, 10, 15]:
        pos, full, h1, h2, lo, hi = ev(f, s, band, k)
        print(f'({f:2d},{s:2d},{band:.4f},k={k:2d}) full {full["net_pct"]:+5.2f}% '
              f'h1 {h1["net_pct"]:+5.2f}% h2 {h2["net_pct"]:+5.2f}% '
              f'trades {full["trades"]:2d} dd {full["max_dd_pct"]:+5.2f}% '
              f'5bps {lo["net_pct"]:+5.2f}% 20bps {hi["net_pct"]:+5.2f}%')

print()
print('=== warmup on (20,50,0.0015,k=10) ===')
for w in [0, 100, 150, 200]:
    pos, full, h1, h2, lo, hi = ev(20, 50, 0.0015, 10, warmup=w)
    print(f'warmup {w:3d}: full {full["net_pct"]:+5.2f}% h1 {h1["net_pct"]:+5.2f}% '
          f'h2 {h2["net_pct"]:+5.2f}% trades {full["trades"]} '
          f'5bps {lo["net_pct"]:+5.2f}% 20bps {hi["net_pct"]:+5.2f}%')

print()
print('=== trade log (20,50,0.0015,k=10,warmup=150) ===')
pos, full, h1, h2, lo, hi = ev(20, 50, 0.0015, 10, warmup=150)
exec_pos = np.zeros(n)
exec_pos[1:] = pos[:-1]
dpos = np.diff(exec_pos, prepend=0.0)
for i in np.where(np.abs(dpos) > 1e-9)[0]:
    print(f'  bar {i:4d} price {c[i]:8.2f} pos {exec_pos[i-1]:+.0f} -> {exec_pos[i]:+.0f}')
print(f'  final pos {exec_pos[-1]:+.0f}')
print(f'  net ${full["net_pnl"]:.1f} ({full["net_pct"]:.2f}%), gross ${full["gross_pnl"]:.1f}, '
      f'costs ${full["costs"]:.1f}, maxDD {full["max_dd_pct"]:.2f}%')
