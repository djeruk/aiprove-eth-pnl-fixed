#!/usr/bin/env python3
"""Round 2: regime-aware candidates + cost sensitivity."""
import numpy as np
import pandas as pd
from sweep import load, backtest, ema, rsi

df = load()
c = df['close'].to_numpy()
h = df['high'].to_numpy()
l = df['low'].to_numpy()
n = len(df)
half = n // 2


def atr(high, low, close, n=14):
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)),
                                           np.abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    return pd.Series(tr).ewm(span=n, adjust=False).mean().to_numpy()


A = atr(h, l, c)


def hyst_persist(f, s, band, k):
    """EMA hysteresis, but a flip needs `k` consecutive bars beyond the band."""
    ef, es = ema(c, f), ema(c, s)
    spread = (ef - es) / es
    pos = np.zeros(n)
    cur = 0.0
    up = dn = 0
    for i in range(n):
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


def dual_mom(ns, nl):
    ms = pd.Series(c).pct_change(ns).to_numpy()
    ml = pd.Series(c).pct_change(nl).to_numpy()
    return np.where((ms > 0) & (ml > 0), 1.0,
                    np.where((ms < 0) & (ml < 0), -1.0, 0.0))


def breakdown(N, entry, exit_):
    """Short on a real N-bar breakdown, cover on recovery; symmetric long."""
    mom = pd.Series(c).pct_change(N).to_numpy()
    pos = np.zeros(n)
    cur = 0.0
    for i in range(n):
        if cur == 0:
            if mom[i] < -entry:
                cur = -1.0
            elif mom[i] > entry:
                cur = 1.0
        elif cur == -1.0 and mom[i] > exit_:
            cur = 0.0
        elif cur == 1.0 and mom[i] < -exit_:
            cur = 0.0
        pos[i] = cur
    return pos


def ema_slow_filter(f, s, slow, band):
    ef, es = ema(c, f), ema(c, s)
    eslow = ema(c, slow)
    spread = (ef - es) / es
    pos = np.zeros(n)
    cur = 0.0
    for i in range(n):
        if spread[i] > band and c[i] > eslow[i]:
            cur = 1.0
        elif spread[i] < -band and c[i] < eslow[i]:
            cur = -1.0
        elif abs(spread[i]) < band * 0.25:
            cur = 0.0
        pos[i] = cur
    return pos


def keltner(N, k, exit_k=0.0):
    mid = ema(c, N)
    pos = np.zeros(n)
    cur = 0.0
    for i in range(n):
        if c[i] < mid[i] - k * A[i]:
            cur = -1.0
        elif c[i] > mid[i] + k * A[i]:
            cur = 1.0
        elif exit_k is not None and abs(c[i] - mid[i]) < exit_k * A[i]:
            cur = 0.0
        pos[i] = cur
    return pos


def donchian_slow(N, slow):
    hi = pd.Series(h).rolling(N).max().to_numpy()
    lo = pd.Series(l).rolling(N).min().to_numpy()
    eslow = ema(c, slow)
    pos = np.zeros(n)
    cur = 0.0
    for i in range(1, n):
        if not np.isnan(hi[i - 1]):
            if c[i] > hi[i - 1] and c[i] > eslow[i]:
                cur = 1.0
            elif c[i] < lo[i - 1] and c[i] < eslow[i]:
                cur = -1.0
        pos[i] = cur
    return pos


cands = {}
for k in [5, 10, 20, 30]:
    cands[f'hyst_persist_12_26_0.001_{k}'] = hyst_persist(12, 26, 0.001, k)
for ns, nl in [(30, 120), (60, 240), (15, 60)]:
    cands[f'dual_mom_{ns}_{nl}'] = dual_mom(ns, nl)
for N, e, x in [(60, 0.008, 0.005), (60, 0.006, 0.003), (120, 0.008, 0.005),
                (30, 0.006, 0.003), (60, 0.010, 0.005)]:
    cands[f'breakdown_{N}_{e}_{x}'] = breakdown(N, e, x)
for slow, band in [(200, 0.001), (200, 0.002), (100, 0.001)]:
    cands[f'ema_slowfilt_12_26_{slow}_{band}'] = ema_slow_filter(12, 26, slow, band)
for N, k in [(20, 2.0), (20, 2.5), (50, 2.0)]:
    cands[f'keltner_{N}_{k}'] = keltner(N, k)
for N, slow in [(55, 200), (100, 200)]:
    cands[f'donch_slow_{N}_{slow}'] = donchian_slow(N, slow)

rows = []
for name, pos in cands.items():
    pos = np.nan_to_num(pos, nan=0.0)
    full = backtest(c, pos)
    h1 = backtest(c[:half], pos[:half])
    h2 = backtest(c[half:], pos[half:])
    # cost sensitivity: 5 and 20 bps/side
    lo = backtest(c, pos, fee_bps=5, slip_bps=0)
    hi = backtest(c, pos, fee_bps=20, slip_bps=0)
    rows.append({
        'name': name,
        'full_%': round(full['net_pct'], 2),
        'h1_%': round(h1['net_pct'], 2),
        'h2_%': round(h2['net_pct'], 2),
        'trades': full['trades'],
        'dd_%': round(full['max_dd_pct'], 2),
        'at5bps_%': round(lo['net_pct'], 2),
        'at20bps_%': round(hi['net_pct'], 2),
        'final_pos': int(pos[-1]),
    })
t = pd.DataFrame(rows).sort_values('full_%', ascending=False)
pd.set_option('display.width', 220)
print(t.to_string(index=False))
