"""
Rolling walk-forward parameter optimization.

Supports two strategy modes:
  ma     — MA crossover only, sweep (ma_fast, ma_slow)
  combo  — MA + RSI + MACD majority, sweep (ma_fast, ma_slow, rsi_threshold)
           MACD fixed at standard (12, 26, 9)

Usage:
  python -m tools.optimize                    # MA-only on default tickers
  python -m tools.optimize --combo            # combo on default tickers
  python -m tools.optimize --combo SPMO QQQ
"""

import sys
import itertools
from collections import defaultdict
import pandas as pd

from core import config
from core.data import fetch
from core.metrics import calc
from core.simulator import run as simulate
import signals.ma   as sig_ma
import signals.rsi  as sig_rsi
import signals.macd as sig_macd
from signals.combo import majority_of
from strategies import momentum

TRAIN_START     = "2020-01-01"
FIRST_TEST_YEAR = 2022
HOLDOUT_YEAR    = 2025   # folds from this year onward are never used in selection
TOP_N           = 5

# MA-only sweep
MA_FAST_WINDOWS = [10, 20, 30, 50]
MA_SLOW_WINDOWS = [50, 100, 150, 200]

# Combo sweep (MA + RSI + MACD majority)
RSI_THRESHOLDS  = [45, 50, 55]   # RSI period fixed at 14
MACD_PARAMS     = (12, 26, 9)    # standard MACD, not swept


def _simulate(prices, signal):
    pos    = momentum.positions(signal)
    result = simulate(prices, pos)
    m      = calc(result["equity"])
    m["margin_calls"] = result["margin_calls"]
    m["total_fees"]   = result["total_fees"]
    return m


def _ma_signal(prices, fast, slow):
    return sig_ma.signal(prices, fast, slow)


def _combo_signal(prices, fast, slow, rsi_thresh):
    ma   = sig_ma.signal(prices, fast, slow)
    rsi  = sig_rsi.signal(prices, threshold=rsi_thresh)
    macd = sig_macd.signal(prices, *MACD_PARAMS)
    return majority_of([ma, rsi, macd])


def _build_combos(mode):
    ma_pairs = [(f, s) for f, s in
                itertools.product(MA_FAST_WINDOWS, MA_SLOW_WINDOWS) if f < s]
    if mode == "combo":
        return [(f, s, r) for (f, s), r in
                itertools.product(ma_pairs, RSI_THRESHOLDS)]
    return [(f, s) for f, s in ma_pairs]


def _run_params(prices, params, mode):
    try:
        if mode == "combo":
            fast, slow, rsi_thresh = params
            sig = _combo_signal(prices, fast, slow, rsi_thresh)
        else:
            fast, slow = params
            sig = _ma_signal(prices, fast, slow)

        if len(sig) < 20:
            return None
        return {**_simulate(prices, sig), "params": params}
    except Exception:
        return None


def _param_label(params, mode):
    if mode == "combo":
        fast, slow, rsi_thresh = params
        return f"MA{fast}/{slow} RSI>{rsi_thresh}"
    fast, slow = params
    return f"MA {fast}/{slow}"


def _bah(prices):
    return calc(config.INITIAL_CAPITAL * (prices / prices.iloc[0]))


def _build_folds(prices):
    folds = []
    current_year = pd.Timestamp.now().year
    for test_year in range(FIRST_TEST_YEAR, current_year + 1):
        train = prices[prices.index <= f"{test_year - 1}-12-31"]
        oos   = prices[(prices.index >= f"{test_year}-01-01") &
                       (prices.index <= f"{test_year}-12-31")]
        min_len = max(MA_SLOW_WINDOWS) + 10
        if len(train) < min_len or len(oos) < 20:
            continue
        folds.append((train, oos, test_year))
    return folds


def run(tickers, mode="ma"):
    combos       = _build_combos(mode)
    current_year = pd.Timestamp.now().year
    strategy_name = "MA + RSI + MACD majority" if mode == "combo" else "MA crossover"

    print(f"\nRolling walk-forward optimization — {strategy_name}")
    print(f"Train start   : {TRAIN_START}  (expanding window)")
    print(f"OOS folds     : {FIRST_TEST_YEAR}–{current_year}  (1 year each)")
    print(f"Combinations  : {len(combos)}")
    print(f"Constraints   : max_dd > {config.MAX_DRAWDOWN_LIMIT:.0%}, "
          f"margin calls = {config.MAX_MARGIN_CALLS}")

    for ticker in tickers:
        prices = fetch(ticker, start=TRAIN_START)
        folds  = _build_folds(prices)
        if not folds:
            print(f"\n{ticker}: not enough data.")
            continue

        print(f"\n{'='*70}")
        print(f"  {ticker}")
        print(f"{'='*70}")

        appearances = defaultdict(int)
        oos_records = []

        for train, oos, test_year in folds:
            fold_label = f"{test_year} OOS  (train: {TRAIN_START[:4]}–{test_year-1})"

            # Sweep on training data
            results = []
            for params in combos:
                m = _run_params(train, params, mode)
                if m:
                    results.append(m)

            if not results:
                continue

            df = pd.DataFrame(results)
            passing = df[
                (df["max_dd"] >= config.MAX_DRAWDOWN_LIMIT) &
                (df["margin_calls"] <= config.MAX_MARGIN_CALLS)
            ].sort_values("cagr", ascending=False).head(TOP_N)

            for _, row in passing.iterrows():
                appearances[row["params"]] += 1

            bah = _bah(oos)
            for _, row in passing.iterrows():
                m = _run_params(oos, row["params"], mode)
                if m:
                    oos_records.append({
                        "fold":    fold_label,
                        "label":   _param_label(row["params"], mode),
                        "params":  row["params"],
                        **{f"oos_{k}": v for k, v in m.items() if k != "params"},
                        "bah_cagr": bah["cagr"],
                    })

        # Per-fold OOS table
        oos_df = pd.DataFrame(oos_records)
        if oos_df.empty:
            print("  No results passed constraints.")
            continue

        print(f"\n  Per-fold OOS results:")
        w = 24 if mode == "combo" else 12
        print(f"  {'Fold':<32} {'Params':<{w}} {'CAGR':>7} {'MaxDD':>7} "
              f"{'vs B&H':>8} {'Pass?':>6}")
        print(f"  {'-'*32} {'-'*w} {'-'*7} {'-'*7} {'-'*8} {'-'*6}")

        for _, r in oos_df.iterrows():
            passes = (r["oos_max_dd"] >= config.MAX_DRAWDOWN_LIMIT and
                      r["oos_margin_calls"] <= config.MAX_MARGIN_CALLS)
            diff = r["oos_cagr"] - r["bah_cagr"]
            print(f"  {r['fold']:<32} {r['label']:<{w}}  "
                  f"{r['oos_cagr']:>6.1%}  {r['oos_max_dd']:>6.1%}  "
                  f"{diff:>+7.1%}  {'YES' if passes else 'NO':>6}")

        # Consistency ranking
        print(f"\n  Consistency (appearances in top {TOP_N} across {len(folds)} folds):")
        print(f"  {'Params':<{w}} {'Count':>6} {'Avg CAGR':>10} "
              f"{'Avg MaxDD':>10} {'Avg vs B&H':>12}")
        print(f"  {'-'*w} {'-'*6} {'-'*10} {'-'*10} {'-'*12}")

        ranked = sorted(appearances.items(), key=lambda x: x[1], reverse=True)
        for params, count in ranked[:TOP_N]:
            label = _param_label(params, mode)
            sub   = oos_df[oos_df["params"].apply(lambda p: p == params)]
            if sub.empty:
                continue
            print(f"  {label:<{w}} {count:>6}  "
                  f"{sub['oos_cagr'].mean():>9.1%}  "
                  f"{sub['oos_max_dd'].mean():>9.1%}  "
                  f"{(sub['oos_cagr'] - sub['bah_cagr']).mean():>+11.1%}")

        if ranked:
            best = ranked[0][0]
            print(f"\n  Recommended: {_param_label(best, mode)}")


def run_final_test(tickers, mode="ma"):
    """
    Two-stage final validation:
      Stage 1 — walk-forward on folds FIRST_TEST_YEAR..HOLDOUT_YEAR-1 to select params
      Stage 2 — run selected params on HOLDOUT_YEAR..present (touched once, never before)
    """
    combos        = _build_combos(mode)
    strategy_name = "MA + RSI + MACD majority" if mode == "combo" else "MA crossover"

    print(f"\n{'='*70}")
    print(f"  FINAL HELD-OUT TEST — {strategy_name}")
    print(f"  Optimization folds : {FIRST_TEST_YEAR}–{HOLDOUT_YEAR - 1}  (never saw holdout)")
    print(f"  Holdout period     : {HOLDOUT_YEAR}–present  (touched once, right now)")
    print(f"{'='*70}")

    for ticker in tickers:
        prices = fetch(ticker, start=TRAIN_START)

        # Stage 1: walk-forward on pre-holdout folds only
        opt_folds = [f for f in _build_folds(prices) if f[2] < HOLDOUT_YEAR]
        if not opt_folds:
            print(f"\n{ticker}: not enough optimization folds.")
            continue

        appearances = defaultdict(int)
        print(f"\n  {ticker} — Stage 1: selecting params on folds "
              f"{FIRST_TEST_YEAR}–{HOLDOUT_YEAR - 1}")

        for train, oos, test_year in opt_folds:
            results = []
            for params in combos:
                m = _run_params(train, params, mode)
                if m:
                    results.append(m)

            if not results:
                continue

            df = pd.DataFrame(results)
            passing = df[
                (df["max_dd"] >= config.MAX_DRAWDOWN_LIMIT) &
                (df["margin_calls"] <= config.MAX_MARGIN_CALLS)
            ].sort_values("cagr", ascending=False).head(TOP_N)

            for _, row in passing.iterrows():
                appearances[row["params"]] += 1

        if not appearances:
            print(f"  No params passed constraints in optimization folds.")
            continue

        ranked      = sorted(appearances.items(), key=lambda x: x[1], reverse=True)
        best_params = ranked[0][0]
        print(f"  Selected params    : {_param_label(best_params, mode)}  "
              f"(appeared in top {TOP_N} in {ranked[0][1]}/{len(opt_folds)} folds)")

        print(f"\n  Runner-up params:")
        for params, count in ranked[1:4]:
            print(f"    {_param_label(params, mode)}  — {count}/{len(opt_folds)} folds")

        # Stage 2: run selected params on holdout (2025–present)
        holdout = prices[prices.index >= f"{HOLDOUT_YEAR}-01-01"]
        if len(holdout) < 30:
            print(f"  Not enough holdout data yet.")
            continue

        bah_holdout   = _bah(holdout)
        result_holdout = _run_params(holdout, best_params, mode)

        print(f"\n  {ticker} — Stage 2: final holdout test "
              f"({HOLDOUT_YEAR}–present, {len(holdout)} days)")
        print(f"\n  {'':30s} {'Buy&Hold':>10} {'Strategy':>10}")

        if result_holdout:
            m = result_holdout
            passes = (m["max_dd"] >= config.MAX_DRAWDOWN_LIMIT and
                      m["margin_calls"] <= config.MAX_MARGIN_CALLS)
            print(f"  {'Total return':30s} {bah_holdout['total']:>10.1%} {m['total']:>10.1%}")
            print(f"  {'CAGR':30s} {bah_holdout['cagr']:>10.1%} {m['cagr']:>10.1%}")
            print(f"  {'Sharpe':30s} {bah_holdout['sharpe']:>10.2f} {m['sharpe']:>10.2f}")
            print(f"  {'Max drawdown':30s} {bah_holdout['max_dd']:>10.1%} {m['max_dd']:>10.1%}")
            print(f"  {'Margin calls':30s} {'':>10} {m['margin_calls']:>10}")
            print(f"  {'Total fees':30s} {'':>10} ${m['total_fees']:>9,.2f}")
            print(f"\n  Constraints passed: {'YES' if passes else 'NO'}")
            print(f"  vs Buy & Hold CAGR: {m['cagr'] - bah_holdout['cagr']:+.1%}")
        else:
            print("  Could not run strategy on holdout data.")


if __name__ == "__main__":
    args    = sys.argv[1:]
    mode    = "combo" if "--combo" in args else "ma"
    final   = "--final" in args
    tickers = [a for a in args if not a.startswith("--")] or ["SPMO"]

    if final:
        run_final_test(tickers, mode=mode)
    else:
        run(tickers, mode=mode)
