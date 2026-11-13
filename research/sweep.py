#!/usr/bin/env python3
"""Candidate-strategy sweep for AIProve eth-pnl-fixed.

Execution model (no lookahead, no phantom fills):
  - Signal computed on bar i close -> position takes effect at bar i+1 open.
  - Position in [-1, +1] = fraction of capital (long +, short -).
  - Cost per fill: fee_bps + slip_bps, charged on notional traded
    (|position change| * capital). Base case: 10 bps fee + 2 bps slippage.
  - Capital: $10,000 notional. PnL reported in $ and % of capital.
"""
import numpy as np
import pandas as pd

BARS = '/home/hatch/workspace/aiprove/aiprove-repo/challenges/eth-backtest/bars.csv'
CAPITAL = 10_000.0


def load():
    return pd.read_csv(BARS)


def backtest(close, pos, fee_bps=10.0, slip_bps=2.0):
    """pos: target position array aligned to bars; executed at next bar's open
    (approximated by next bar's close for PnL; fills priced at next open)."""
    close = np.asarray(close, dtype=float)
    n = len(close)
    # executed position: pos[i] decided at close of bar i, live from bar i+1
    exec_pos = np.zeros(n)
    exec_pos[1:] = pos[:-1]
    # PnL: position held over bar i earns (close[i]-close[i-1])/close[i-1]
    ret = np.zeros(n)
    ret[1:] = close[1:] / close[:-1] - 1.0
    gross = exec_pos * ret * CAPITAL
    # trades: position changes, priced at the bar where the new position starts
    dpos = np.diff(exec_pos, prepend=0.0)
    traded = np.abs(dpos) * CAPITAL
    cost = traded * (fee_bps + slip_bps) / 1e4
    pnl = gross - cost
    equity = CAPITAL + np.cumsum(pnl)
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    return {
        'net_pnl': float(pnl.sum()),
        'net_pct': float(100 * pnl.sum() / CAPITAL),
        'gross_pnl': float(gross.sum()),
        'costs': float(cost.sum()),
        'trades': int((np.abs(dpos) > 1e-9).sum()),
        'turnover': float(traded.sum() / CAPITAL),
        'max_dd_pct': float(100 * dd.min()),
        'equity': equity,
        'pnl': pnl,
    }


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def rsi(close, n=14):
    d = pd.Series(close).diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50).to_numpy()


def run_all():
    df = load()
    c = df['close'].to_numpy()
    h = df['high'].to_numpy()
    l = df['low'].to_numpy()
    n = len(df)
    half = n // 2

    cands = {}

    # 0. baselines
    cands['buy&hold'] = np.ones(n)
    cands['flat'] = np.zeros(n)

    # 1. EMA crossovers (always in, +/-1)
    for f, s in [(9, 21), (12, 26), (20, 50), (50, 200), (12, 50), (26, 100)]:
        ef, es = ema(c, f), ema(c, s)
        cands[f'ema_{f}_{s}'] = np.where(ef > es, 1.0, -1.0)

    # 2. EMA crossover with hysteresis band (fraction of price)
    for f, s, band in [(12, 26, 0.001), (12, 26, 0.002), (20, 50, 0.001), (20, 50, 0.002)]:
        ef, es = ema(c, f), ema(c, s)
        spread = (ef - es) / es
        pos = np.zeros(n)
        cur = 0.0
        for i in range(n):
            if spread[i] > band:
                cur = 1.0
            elif spread[i] < -band:
                cur = -1.0
            pos[i] = cur
        cands[f'ema_hyst_{f}_{s}_{band}'] = pos

    # 3. Donchian breakout (hold previous inside the channel)
    for N in [20, 55, 100]:
        hi = pd.Series(h).rolling(N).max().to_numpy()
        lo = pd.Series(l).rolling(N).min().to_numpy()
        pos = np.zeros(n)
        cur = 0.0
        for i in range(n):
            if not np.isnan(hi[i]):
                if c[i] > hi[i - 1] if i > 0 else False:
                    cur = 1.0
                elif c[i] < lo[i - 1] if i > 0 else False:
                    cur = -1.0
            pos[i] = cur
        cands[f'donchian_{N}'] = pos

    # 4. Momentum: sign of past N-bar return
    for N in [15, 30, 60, 120, 240]:
        mom = pd.Series(c).pct_change(N).to_numpy()
        cands[f'mom_{N}'] = np.where(mom > 0, 1.0, np.where(mom < 0, -1.0, 0.0))

    # 5. RSI mean reversion (long oversold, short overbought, flat mid)
    for lo_t, hi_t in [(30, 70), (25, 75), (20, 80)]:
        r = rsi(c, 14)
        pos = np.zeros(n)
        cur = 0.0
        for i in range(n):
            if r[i] < lo_t:
                cur = 1.0
            elif r[i] > hi_t:
                cur = -1.0
            elif 45 <= r[i] <= 55:
                cur = 0.0
            pos[i] = cur
        cands[f'rsi_mr_{lo_t}_{hi_t}'] = pos

    # 6. RSI trend (long when RSI strong, short when weak) -- trend variant
    r = rsi(c, 14)
    cands['rsi_trend'] = np.where(r > 55, 1.0, np.where(r < 45, -1.0, 0.0))

    # 7. MACD (12/26/9)
    macd = ema(c, 12) - ema(c, 26)
    sig = ema(macd, 9)
    cands['macd'] = np.where(macd > sig, 1.0, -1.0)

    # 8. Bollinger mean reversion (20, 2sd): short upper, long lower, flat at mid
    mid = pd.Series(c).rolling(20).mean().to_numpy()
    sd = pd.Series(c).rolling(20).std().to_numpy()
    pos = np.zeros(n)
    cur = 0.0
    for i in range(n):
        if not np.isnan(mid[i]):
            if c[i] > mid[i] + 2 * sd[i]:
                cur = -1.0
            elif c[i] < mid[i] - 2 * sd[i]:
                cur = 1.0
            elif abs(c[i] - mid[i]) < 0.3 * sd[i]:
                cur = 0.0
        pos[i] = cur
    cands['boll_mr'] = pos

    # 9. EMA trend + ATR filter: only take trend when |fast-slow| > k*ATR
    for f, s, k in [(12, 26, 0.5), (12, 26, 1.0)]:
        ef, es = ema(c, f), ema(c, s)
        tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
        tr[0] = h[0] - l[0]
        atr = pd.Series(tr).ewm(span=14, adjust=False).mean().to_numpy()
        pos = np.where(ef - es > k * atr, 1.0, np.where(es - ef > k * atr, -1.0, 0.0))
        cands[f'ema_atr_{f}_{s}_{k}'] = pos

    rows = []
    for name, pos in cands.items():
        pos = np.nan_to_num(pos, nan=0.0)
        full = backtest(c, pos)
        h1 = backtest(c[:half], pos[:half])
        h2 = backtest(c[half:], pos[half:])
        rows.append({
            'name': name,
            'full_$': round(full['net_pnl'], 1),
            'full_%': round(full['net_pct'], 2),
            'h1_%': round(h1['net_pct'], 2),
            'h2_%': round(h2['net_pct'], 2),
            'trades': full['trades'],
            'costs_$': round(full['costs'], 1),
            'dd_%': round(full['max_dd_pct'], 2),
        })
    t = pd.DataFrame(rows).sort_values('full_$', ascending=False)
    pd.set_option('display.width', 200)
    print(t.to_string(index=False))
    return t


if __name__ == '__main__':
    run_all()
