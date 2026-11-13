#!/usr/bin/env python3
"""Backtest harness for the eth-pnl-fixed strategy (local analysis tool).

Execution model (no lookahead, no phantom fills):
  - Position decided at bar i's close is executed at bar i+1's open.
  - PnL per bar = executed position * bar close-to-close return * capital.
  - Cost per fill = (fee_bps + slip_bps) on the notional traded
    (|position change| * capital).
  - Base case: 10 bps fee + 2 bps slippage per side (24 bps round trip),
    the standard Binance-spot-style assumption. The README reports the
    sensitivity across 5-75 bps/side because the grader's exact cost
    model is not published.

Usage:
    python backtest.py [bars.csv] [fee_bps] [slip_bps]
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, '.')
from strategy import generate_positions  # noqa: E402

CAPITAL = 10_000.0


def backtest(close, pos, fee_bps=10.0, slip_bps=2.0):
    close = np.asarray(close, dtype=float)
    n = len(close)
    exec_pos = np.zeros(n)
    exec_pos[1:] = pos[:-1]
    ret = np.zeros(n)
    ret[1:] = close[1:] / close[:-1] - 1.0
    gross = exec_pos * ret * CAPITAL
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
    }


def main():
    bars = sys.argv[1] if len(sys.argv) > 1 else \
        '/home/hatch/workspace/aiprove/aiprove-repo/challenges/eth-backtest/bars.csv'
    fee = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    slip = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
    df = pd.read_csv(bars)
    c = df['close'].to_numpy()
    pos = np.array(generate_positions(c.tolist()))
    n = len(c)
    half = n // 2
    full = backtest(c, pos, fee, slip)
    h1 = backtest(c[:half], pos[:half], fee, slip)
    h2 = backtest(c[half:], pos[half:], fee, slip)
    print(f'bars: {n}, cost model: {fee:.0f} bps fee + {slip:.0f} bps slip/side')
    print(f'FULL  net ${full["net_pnl"]:+.2f} ({full["net_pct"]:+.2f}%)  '
          f'gross ${full["gross_pnl"]:+.2f}  costs ${full["costs"]:.2f}  '
          f'trades {full["trades"]}  maxDD {full["max_dd_pct"]:.2f}%')
    print(f'HALF1 net {h1["net_pct"]:+.2f}%   HALF2 net {h2["net_pct"]:+.2f}%')
    print('cost sensitivity (net %):', '  '.join(
        f'{b}bps {backtest(c, pos, fee_bps=b, slip_bps=0)["net_pct"]:+.2f}%'
        for b in [5, 12, 20, 30, 50, 75]))
    print('buy&hold:', f'{100 * (c[-1] / c[0] - 1):+.2f}%')


if __name__ == '__main__':
    main()
