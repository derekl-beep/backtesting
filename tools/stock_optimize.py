"""
Walk-forward MA parameter optimizer for the three-tier momentum stock strategy.

Sweeps (fast, mid) MA pairs with slow fixed at 200.
Uses the same expanding-window OOS framework as tools/optimize.py.

Usage:
  python -m tools.stock_optimize NVDA
  python -m tools.stock_optimize NVDA MSFT AAPL
"""

import sys
import itertools
from collections import defaultdict
import pandas as pd

from core import config
from core.data import fetch
from core.metrics import calc
from core.simulator import run as simulate
from signals import ma_3tier as sig_3t
from strategies import momentum_3t as strat_3t

SLOW_MA         = 200
MA_FAST_WINDOWS = [10, 20, 30, 50]
MA_MID_WINDOWS  = [50, 75, 100, 150]
TRAIN_START     = "2020-01-01"
FIRST_TEST_YEAR = 2022
TOP_N           = 5


def _combos():
    return [
        {"fast": f, "mid": m}
        for f, m in itertools.product(MA_FAST_WINDOWS, MA_MID_WINDOWS)
        if f < m
    ]


def _label(fast, mid):
    return f"MA{fast}/{mid}/{SLOW_MA}"


def _run(prices, fast, mid):
    try:
        sig = sig_3t.signal(prices, fast, mid, SLOW_MA)
        if len(sig) < 20:
            return None
        pos    = strat_3t.positions(sig)
        result = simulate(prices, pos)
        m      = calc(result["equity"])
        m["margin_calls"] = result["margin_calls"]
        m["total_fees"]   = result["total_fees"]
        return m
    except Exception:
        return None


def _bah(prices):
    return calc(config.INITIAL_CAPITAL * (prices / prices.iloc[0]))


def _build_folds(prices):
    folds = []
    current_year = pd.Timestamp.now().year
    for test_year in range(FIRST_TEST_YEAR, current_year + 1):
        train = prices[prices.index <= f"{test_year - 1}-12-31"]
        oos   = prices[(prices.index >= f"{test_year}-01-01") &
                       (prices.index <= f"{test_year}-12-31")]
        if len(train) < SLOW_MA + 10 or len(oos) < 20:
            continue
        folds.append((train, oos, test_year))
    return folds


def _print_table(oos_df, appearances, n_folds):
    w = max(len(r["label"]) for _, r in oos_df.iterrows()) + 2

    print(f"\n  Per-fold OOS results:")
    print(f"  {'Fold':<32} {'Params':<{w}} {'CAGR':>7} {'MaxDD':>7} "
          f"{'vs B&H':>8} {'Pass?':>6}")
    print(f"  {'-'*32} {'-'*w} {'-'*7} {'-'*7} {'-'*8} {'-'*6}")

    for _, r in oos_df.iterrows():
        passes = (r["oos_max_dd"] >= config.MAX_DRAWDOWN_LIMIT and
                  r["oos_margin_calls"] <= config.MAX_MARGIN_CALLS)
        diff = r["oos_cagr"] - r["bah_cagr"]
        print(f"  {r['fold']:<32} {r['label']:<{w}} "
              f"{r['oos_cagr']:>6.1%}  {r['oos_max_dd']:>6.1%}  "
              f"{diff:>+7.1%}  {'YES' if passes else 'NO':>6}")

    print(f"\n  Consistency (top {TOP_N} across {n_folds} folds):")
    print(f"  {'Params':<{w}} {'Count':>6} {'Avg CAGR':>10} "
          f"{'Avg MaxDD':>10} {'Avg vs B&H':>12}")
    print(f"  {'-'*w} {'-'*6} {'-'*10} {'-'*10} {'-'*12}")

    ranked = sorted(appearances.items(), key=lambda x: x[1], reverse=True)
    for (fast, mid), count in ranked[:TOP_N]:
        label = _label(fast, mid)
        sub   = oos_df[(oos_df["fast"] == fast) & (oos_df["mid"] == mid)]
        if sub.empty:
            continue
        print(f"  {label:<{w}} {count:>6}  "
              f"{sub['oos_cagr'].mean():>9.1%}  "
              f"{sub['oos_max_dd'].mean():>9.1%}  "
              f"{(sub['oos_cagr'] - sub['bah_cagr']).mean():>+11.1%}")

    return ranked


def optimize(ticker: str, combos: list) -> dict | None:
    prices = fetch(ticker, start=TRAIN_START)
    folds  = _build_folds(prices)
    if not folds:
        print(f"\n{ticker}: not enough data for OOS folds.")
        return None

    print(f"\n{'='*70}")
    print(f"  {ticker}  (slow MA fixed at {SLOW_MA})")
    print(f"{'='*70}")

    appearances = defaultdict(int)
    oos_records = []

    for train, oos, test_year in folds:
        fold_label = f"{test_year} OOS  (train: {TRAIN_START[:4]}–{test_year-1})"

        results = []
        for c in combos:
            m = _run(train, c["fast"], c["mid"])
            if m:
                m["fast"] = c["fast"]
                m["mid"]  = c["mid"]
                results.append(m)
        if not results:
            continue

        df = pd.DataFrame(results)
        passing = df[
            (df["max_dd"] >= config.MAX_DRAWDOWN_LIMIT) &
            (df["margin_calls"] <= config.MAX_MARGIN_CALLS)
        ].sort_values("cagr", ascending=False).head(TOP_N)

        for _, row in passing.iterrows():
            appearances[(int(row["fast"]), int(row["mid"]))] += 1

        bah = _bah(oos)
        for _, row in passing.iterrows():
            m = _run(oos, int(row["fast"]), int(row["mid"]))
            if m:
                oos_records.append({
                    "fold":     fold_label,
                    "label":    _label(int(row["fast"]), int(row["mid"])),
                    "fast":     int(row["fast"]),
                    "mid":      int(row["mid"]),
                    **{f"oos_{k}": v for k, v in m.items()},
                    "bah_cagr": bah["cagr"],
                })

    if not oos_records:
        print("  No results passed constraints.")
        return None

    oos_df = pd.DataFrame(oos_records)
    ranked = _print_table(oos_df, appearances, len(folds))

    if ranked:
        best_fast, best_mid = ranked[0][0]
        print(f"\n  Recommended: {_label(best_fast, best_mid)}")
        print(f"  Use: python -m tools.stock_backtest {ticker} "
              f"--strategy momentum_3t --ma {best_fast}:{best_mid}")
        return {"fast": best_fast, "mid": best_mid, "slow": SLOW_MA}

    return None


if __name__ == "__main__":
    tickers = [a.upper() for a in sys.argv[1:]] if sys.argv[1:] else ["NVDA"]
    combos  = _combos()

    print(f"\nThree-tier MA optimization  (slow fixed at {SLOW_MA})")
    print(f"Fast windows : {MA_FAST_WINDOWS}")
    print(f"Mid windows  : {MA_MID_WINDOWS}")
    print(f"Combinations : {len(combos)}")
    print(f"OOS folds    : {FIRST_TEST_YEAR}–present")
    print(f"Constraints  : max_dd > {config.MAX_DRAWDOWN_LIMIT:.0%}, "
          f"margin calls = {config.MAX_MARGIN_CALLS}")

    for ticker in tickers:
        optimize(ticker, combos)
