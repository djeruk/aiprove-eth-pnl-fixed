#!/usr/bin/env python3
"""Round 3: trade-log inspection + parameter plateau check for hyst_persist."""
import numpy as np
import pandas as pd
from sweep import load, backtest, ema

df = load()
c = df['close'].to_numpy()
n = len(df)
half = n // 2


def hyst_persist(f, s, band, k, warmup=0):
    ef, es = ema(c, f), ema(c, s)
    spread = (ef - es) / es
    pos = np.zeros(n)
    cur = 0.0
    up = dn = 0
    for i in range(n):
        if i < warmup:
            pos[i] = 0.0
            continue
        if spread[i] > band:
            up += 1
            dn = 0
        elif spread[i] < -band:
            dn += 1
            up = 0
        else:
            up = dn = 0
        if up >= k:
            cur = 1.0
        elif dn >= k:
            cur = -1.0
        pos[i] = cur
    return pos


def trade_log(pos, label):
    exec_pos = np.zeros(n)
    exec_pos[1:] = pos[:-1]
    dpos = np.diff(exec_pos, prepend=0.0)
    print(f'--- {label} ---')
    for i in np.where(np.abs(dpos) > 1e-9)[0]:
        print(f'  bar {i:4d} price {c[i]:8.2f} pos {exec_pos[i-1]:+.0f} -> {exec_pos[i]:+.0f}')
    print(f'  final pos {exec_pos[-1]:+.0f}')


for k in [5, 10]:
    trade_log(hyst_persist(12, 26, 0.001, k), f'k={k}')

print()
print('=== parameter plateau (net % at base cost 12bps/side) ===')
print('rows: (fast,slow,band)  cols: k=5, k=10, k=15   [h1% / h2% for k=10]')
results = {}
for f, s in [(9, 21), (12, 26), (20, 50)]:
    for band in [0.0005, 0.001, 0.0015, 0.002]:
        row = []
        for k in [5, 10, 15]:
            pos = hyst_persist(f, s, band, k)
            r = backtest(c, pos)
            row.append(r['net_pct'])
            results[(f, s, band, k)] = r
        h1 = backtest(c[:half], hyst_persist(f, s, band, 10)[:half])['net_pct']
        h2 = backtest(c[half:], hyst_persist(f, s, band, 10)[half:])['net_pct']
        print(f'({f:2d},{s:3d},{band:.4f})  ' + '  '.join(f'{v:+6.2f}' for v in row)
              + f'   | k=10: h1 {h1:+.2f} h2 {h2:+.2f}')

print()
print('=== warmup effect on (12,26,0.001,k=10) ===')
for w in [0, 50, 100, 200]:
    pos = hyst_persist(12, 26, 0.001, 10, warmup=w)
    r = backtest(c, pos)
    h1 = backtest(c[:half], pos[:half])['net_pct']
    h2 = backtest(c[half:], pos[half:])['net_pct']
    print(f'warmup {w:3d}: full {r["net_pct"]:+.2f}%  h1 {h1:+.2f}%  h2 {h2:+.2f}%  trades {r["trades"]}')
