"""
Rolling walk-forward parameter optimization.

Sweeps params for the selected signal combination.
Each signal set finds its own optimal params independently.

Signals:
  ma    — MA crossover:   sweeps (ma_fast, ma_slow)
  rsi   — RSI threshold:  sweeps (rsi_threshold), period fixed at 14
  macd  — MACD crossover: fixed at (12, 26, 9), just included/excluded

Combination: majority vote when 2+ signals included.

Usage:
  python -m tools.optimize --signals ma
  python -m tools.optimize --signals ma,rsi
  python -m tools.optimize --signals ma,rsi,macd SPMO QQQ
  python -m tools.optimize --signals ma,rsi,macd --final SPMO
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
HOLDOUT_YEAR    = 2025
TOP_N           = 5

# Parameter grids per signal
MA_FAST_WINDOWS = [10, 20, 30, 50]
MA_SLOW_WINDOWS = [50, 100, 150, 200]
RSI_THRESHOLDS  = [45, 50, 55]
MACD_PARAMS     = (12, 26, 9)   # fixed — standard, not swept


def _build_signal(prices, params: dict, signals: set):
    """Build combined signal from included components using given params."""
    parts = []
    if "ma" in signals:
        parts.append(sig_ma.signal(prices, params["ma_fast"], params["ma_slow"]))
    if "rsi" in signals:
        parts.append(sig_rsi.signal(prices, threshold=params.get("rsi_threshold", 50)))
    if "macd" in signals:
        parts.append(sig_macd.signal(prices, *MACD_PARAMS))

    if len(parts) == 1:
        return parts[0]
    return majority_of(parts)


def _build_combos(signals: set) -> list[dict]:
    """Build cartesian product of param grids for included signals."""
    grids = {}
    if "ma" in signals:
        grids["ma"] = [
            {"ma_fast": f, "ma_slow": s}
            for f, s in itertools.product(MA_FAST_WINDOWS, MA_SLOW_WINDOWS) if f < s
        ]
    if "rsi" in signals:
        grids["rsi"] = [{"rsi_threshold": t} for t in RSI_THRESHOLDS]

    if not grids:
        return [{}]

    # Cartesian product across signal param groups, merge dicts
    combos = [{}]
    for group in grids.values():
        combos = [{**a, **b} for a in combos for b in group]
    return combos


def _param_label(params: dict, signals: set) -> str:
    parts = []
    if "ma" in signals:
        parts.append(f"MA{params.get('ma_fast','?')}/{params.get('ma_slow','?')}")
    if "rsi" in signals:
        parts.append(f"RSI>{params.get('rsi_threshold', 50)}")
    if "macd" in signals:
        parts.append("MACD")
    return " ".join(parts)


def _run_params(prices, params: dict, signals: set):
    try:
        sig = _build_signal(prices, params, signals)
        if len(sig) < 20:
            return None
        pos    = momentum.positions(sig)
        result = simulate(prices, pos)
        m      = calc(result["equity"])
        m["margin_calls"] = result["margin_calls"]
        m["total_fees"]   = result["total_fees"]
        m["params"]       = params
        return m
    except Exception:
        return None


def _bah(prices):
    return calc(config.INITIAL_CAPITAL * (prices / prices.iloc[0]))


def _build_folds(prices, last_year=None):
    folds = []
    current_year = last_year or pd.Timestamp.now().year
    for test_year in range(FIRST_TEST_YEAR, current_year + 1):
        train = prices[prices.index <= f"{test_year - 1}-12-31"]
        oos   = prices[(prices.index >= f"{test_year}-01-01") &
                       (prices.index <= f"{test_year}-12-31")]
        if len(train) < max(MA_SLOW_WINDOWS) + 10 or len(oos) < 20:
            continue
        folds.append((train, oos, test_year))
    return folds


def _sweep_folds(prices, folds, combos, signals):
    """Run walk-forward sweep. Returns (appearances dict, oos_records list)."""
    appearances = defaultdict(int)
    oos_records = []

    for train, oos, test_year in folds:
        fold_label = f"{test_year} OOS  (train: {TRAIN_START[:4]}–{test_year-1})"

        results = [m for p in combos if (m := _run_params(train, p, signals))]
        if not results:
            continue

        df = pd.DataFrame(results)
        passing = df[
            (df["max_dd"] >= config.MAX_DRAWDOWN_LIMIT) &
            (df["margin_calls"] <= config.MAX_MARGIN_CALLS)
        ].sort_values("cagr", ascending=False).head(TOP_N)

        for _, row in passing.iterrows():
            key = tuple(sorted(row["params"].items()))
            appearances[key] += 1

        bah = _bah(oos)
        for _, row in passing.iterrows():
            m = _run_params(oos, row["params"], signals)
            if m:
                oos_records.append({
                    "fold":     fold_label,
                    "label":    _param_label(row["params"], signals),
                    "params":   row["params"],
                    **{f"oos_{k}": v for k, v in m.items() if k != "params"},
                    "bah_cagr": bah["cagr"],
                })

    return appearances, oos_records


def _print_oos_table(oos_df, appearances, n_folds, signals):
    w = max(len(_param_label(p, signals)) for p in
            [{k: v for k, v in key} for key in appearances] or [{}]) + 2
    w = max(w, 14)

    print(f"\n  Per-fold OOS results:")
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

    print(f"\n  Consistency (appearances in top {TOP_N} across {n_folds} folds):")
    print(f"  {'Params':<{w}} {'Count':>6} {'Avg CAGR':>10} "
          f"{'Avg MaxDD':>10} {'Avg vs B&H':>12}")
    print(f"  {'-'*w} {'-'*6} {'-'*10} {'-'*10} {'-'*12}")

    ranked = sorted(appearances.items(), key=lambda x: x[1], reverse=True)
    for key, count in ranked[:TOP_N]:
        params = {k: v for k, v in key}
        label  = _param_label(params, signals)
        sub    = oos_df[oos_df["params"].apply(lambda p: p == params)]
        if sub.empty:
            continue
        print(f"  {label:<{w}} {count:>6}  "
              f"{sub['oos_cagr'].mean():>9.1%}  "
              f"{sub['oos_max_dd'].mean():>9.1%}  "
              f"{(sub['oos_cagr'] - sub['bah_cagr']).mean():>+11.1%}")

    return ranked


def run(tickers, signals):
    combos = _build_combos(signals)
    sig_desc = " + ".join(sorted(signals)).upper()
    current_year = pd.Timestamp.now().year

    print(f"\nRolling walk-forward optimization")
    print(f"Signals       : {sig_desc}  ({len(combos)} combinations)")
    print(f"Train start   : {TRAIN_START}  (expanding window)")
    print(f"OOS folds     : {FIRST_TEST_YEAR}–{current_year - 1}")
    print(f"Constraints   : max_dd > {config.MAX_DRAWDOWN_LIMIT:.0%}, "
          f"margin calls = {config.MAX_MARGIN_CALLS}")

    for ticker in tickers:
        prices = fetch(ticker, start=TRAIN_START)
        folds  = _build_folds(prices, last_year=current_year - 1)
        if not folds:
            print(f"\n{ticker}: not enough data.")
            continue

        print(f"\n{'='*70}")
        print(f"  {ticker}")
        print(f"{'='*70}")

        appearances, oos_records = _sweep_folds(prices, folds, combos, signals)
        oos_df = pd.DataFrame(oos_records)
        if oos_df.empty:
            print("  No results passed constraints.")
            continue

        ranked = _print_oos_table(oos_df, appearances, len(folds), signals)
        if ranked:
            best_params = {k: v for k, v in ranked[0][0]}
            print(f"\n  Recommended: {_param_label(best_params, signals)}")


def run_final_test(tickers, signals):
    combos    = _build_combos(signals)
    sig_desc  = " + ".join(sorted(signals)).upper()

    print(f"\n{'='*70}")
    print(f"  FINAL HELD-OUT TEST — {sig_desc}")
    print(f"  Optimization folds : {FIRST_TEST_YEAR}–{HOLDOUT_YEAR - 1}")
    print(f"  Holdout period     : {HOLDOUT_YEAR}–present  (touched once, right now)")
    print(f"{'='*70}")

    for ticker in tickers:
        prices    = fetch(ticker, start=TRAIN_START)
        opt_folds = _build_folds(prices, last_year=HOLDOUT_YEAR - 1)
        if not opt_folds:
            print(f"\n{ticker}: not enough optimization folds.")
            continue

        print(f"\n  {ticker} — Stage 1: selecting params on folds "
              f"{FIRST_TEST_YEAR}–{HOLDOUT_YEAR - 1}")

        appearances, _ = _sweep_folds(prices, opt_folds, combos, signals)
        if not appearances:
            print("  No params passed constraints.")
            continue

        ranked      = sorted(appearances.items(), key=lambda x: x[1], reverse=True)
        best_key    = ranked[0][0]
        best_params = {k: v for k, v in best_key}
        print(f"  Selected : {_param_label(best_params, signals)}  "
              f"({ranked[0][1]}/{len(opt_folds)} folds)")
        print(f"  Runner-ups:")
        for key, count in ranked[1:4]:
            print(f"    {_param_label({k:v for k,v in key}, signals)} — "
                  f"{count}/{len(opt_folds)} folds")

        # Stage 2: holdout
        holdout = prices[prices.index >= f"{HOLDOUT_YEAR}-01-01"]
        if len(holdout) < 30:
            print("  Not enough holdout data yet.")
            continue

        bah_h  = _bah(holdout)
        result = _run_params(holdout, best_params, signals)

        print(f"\n  {ticker} — Stage 2: holdout ({HOLDOUT_YEAR}–present, "
              f"{len(holdout)} days)")
        print(f"\n  {'':30s} {'Buy&Hold':>10} {'Strategy':>10}")
        if result:
            passes = (result["max_dd"] >= config.MAX_DRAWDOWN_LIMIT and
                      result["margin_calls"] <= config.MAX_MARGIN_CALLS)
            print(f"  {'Total return':30s} {bah_h['total']:>10.1%} {result['total']:>10.1%}")
            print(f"  {'CAGR':30s} {bah_h['cagr']:>10.1%} {result['cagr']:>10.1%}")
            print(f"  {'Sharpe':30s} {bah_h['sharpe']:>10.2f} {result['sharpe']:>10.2f}")
            print(f"  {'Max drawdown':30s} {bah_h['max_dd']:>10.1%} {result['max_dd']:>10.1%}")
            print(f"  {'Margin calls':30s} {'':>10} {result['margin_calls']:>10}")
            print(f"  {'Total fees':30s} {'':>10} ${result['total_fees']:>9,.2f}")
            print(f"\n  Constraints passed : {'YES' if passes else 'NO'}")
            print(f"  vs Buy & Hold CAGR : {result['cagr'] - bah_h['cagr']:+.1%}")


if __name__ == "__main__":
    args    = sys.argv[1:]
    final   = "--final" in args
    sig_arg = next((a for a in args if a.startswith("--signals=")), None)
    if sig_arg:
        signals = set(sig_arg.split("=")[1].split(","))
    elif "--signals" in args:
        idx     = args.index("--signals")
        signals = set(args[idx + 1].split(","))
    else:
        signals = {"ma", "rsi", "macd"}   # default: full combo

    tickers = [a for a in args
               if not a.startswith("--") and a not in signals
               and "," not in a] or ["SPMO"]

    if final:
        run_final_test(tickers, signals)
    else:
        run(tickers, signals)
