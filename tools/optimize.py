"""
Rolling walk-forward parameter optimization.

Sweeps MA fast/slow windows, filters by hard constraints, validates
top combinations on out-of-sample folds to find robust params.

Usage:
  python -m tools.optimize
  python -m tools.optimize SPMO QQQ
"""

import sys
import itertools
from collections import defaultdict
import pandas as pd

from core import config
from core.data import fetch
from core.metrics import calc
from core.simulator import run as simulate
from signals import ma
from strategies import momentum

TRAIN_START     = "2020-01-01"
FIRST_TEST_YEAR = 2022
TOP_N           = 5
FAST_WINDOWS    = [10, 20, 30, 50]
SLOW_WINDOWS    = [50, 100, 150, 200]


def _run_combo(prices, fast, slow):
    if len(prices) < slow + 10:
        return None
    sig = ma.signal(prices, fast, slow)
    pos = momentum.positions(sig)
    result = simulate(prices, pos)
    m = calc(result["equity"])
    m["margin_calls"] = result["margin_calls"]
    m["total_fees"]   = result["total_fees"]
    return m


def _bah(prices):
    return calc(config.INITIAL_CAPITAL * (prices / prices.iloc[0]))


def _build_folds(prices):
    folds = []
    current_year = pd.Timestamp.now().year
    for test_year in range(FIRST_TEST_YEAR, current_year + 1):
        train = prices[prices.index <= f"{test_year - 1}-12-31"]
        oos   = prices[(prices.index >= f"{test_year}-01-01") &
                       (prices.index <= f"{test_year}-12-31")]
        if len(train) < max(SLOW_WINDOWS) + 10 or len(oos) < 20:
            continue
        folds.append((train, oos, test_year))
    return folds


def run(tickers):
    combos = [(f, s) for f, s in itertools.product(FAST_WINDOWS, SLOW_WINDOWS) if f < s]
    current_year = pd.Timestamp.now().year

    print(f"\nRolling walk-forward validation")
    print(f"Train start   : {TRAIN_START}  (expanding window)")
    print(f"OOS folds     : {FIRST_TEST_YEAR}–{current_year}  (1 year each)")
    print(f"Constraints   : max_dd > {config.MAX_DRAWDOWN_LIMIT:.0%}, margin calls = {config.MAX_MARGIN_CALLS}")

    for ticker in tickers:
        prices = fetch(ticker, start=TRAIN_START)
        folds  = _build_folds(prices)
        if not folds:
            print(f"\n{ticker}: not enough data.")
            continue

        print(f"\n{'='*65}")
        print(f"  {ticker}")
        print(f"{'='*65}")

        appearances = defaultdict(int)
        oos_records = []

        for train, oos, test_year in folds:
            fold_label = f"{test_year} OOS  (train: {TRAIN_START[:4]}–{test_year-1})"

            # Sweep on training data
            results = []
            for fast, slow in combos:
                m = _run_combo(train, fast, slow)
                if m:
                    results.append({**m, "fast": fast, "slow": slow})

            df = pd.DataFrame(results)
            passing = df[
                (df["max_dd"] >= config.MAX_DRAWDOWN_LIMIT) &
                (df["margin_calls"] <= config.MAX_MARGIN_CALLS)
            ].sort_values("cagr", ascending=False).head(TOP_N)

            for _, row in passing.iterrows():
                appearances[(int(row.fast), int(row.slow))] += 1

            bah = _bah(oos)
            for _, row in passing.iterrows():
                fast, slow = int(row.fast), int(row.slow)
                m = _run_combo(oos, fast, slow)
                if m:
                    oos_records.append({
                        "fold": fold_label, "fast": fast, "slow": slow,
                        **{f"oos_{k}": v for k, v in m.items()},
                        "bah_cagr": bah["cagr"],
                    })

        # Per-fold OOS table
        print(f"\n  Per-fold OOS results:")
        print(f"  {'Fold':<32} {'MA':>8} {'CAGR':>8} {'MaxDD':>8} {'vs B&H':>8} {'Pass?':>6}")
        print(f"  {'-'*32} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*6}")

        oos_df = pd.DataFrame(oos_records)
        if not oos_df.empty:
            for _, r in oos_df.iterrows():
                passes = (r["oos_max_dd"] >= config.MAX_DRAWDOWN_LIMIT and
                          r["oos_margin_calls"] <= config.MAX_MARGIN_CALLS)
                diff = r["oos_cagr"] - r["bah_cagr"]
                print(f"  {r['fold']:<32} {int(r.fast)}/{int(r.slow):>4}  "
                      f"{r['oos_cagr']:>7.1%}  {r['oos_max_dd']:>7.1%}  "
                      f"{diff:>+7.1%}  {'YES' if passes else 'NO':>6}")

        # Consistency ranking
        print(f"\n  Consistency (top {TOP_N} across {len(folds)} folds):")
        print(f"  {'MA':>8} {'Count':>7} {'Avg CAGR':>10} {'Avg MaxDD':>10} {'Avg vs B&H':>12}")
        print(f"  {'-'*8} {'-'*7} {'-'*10} {'-'*10} {'-'*12}")

        ranked = sorted(appearances.items(), key=lambda x: x[1], reverse=True)
        for (fast, slow), count in ranked[:TOP_N]:
            if oos_df.empty:
                continue
            sub = oos_df[(oos_df.fast == fast) & (oos_df.slow == slow)]
            if sub.empty:
                continue
            print(f"  {fast}/{slow:>4}  {count:>7}  {sub['oos_cagr'].mean():>9.1%}  "
                  f"{sub['oos_max_dd'].mean():>9.1%}  "
                  f"{(sub['oos_cagr'] - sub['bah_cagr']).mean():>+11.1%}")

        if ranked:
            best = ranked[0][0]
            print(f"\n  Recommended: MA {best[0]}/{best[1]}")


if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else config.DEFAULT_TICKERS
    run(tickers)
