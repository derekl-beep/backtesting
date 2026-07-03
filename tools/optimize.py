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

TRAIN_START     = config.START
FIRST_TEST_YEAR = 2018
HOLDOUT_YEAR    = 2025
TOP_N           = 5
MIN_AVG_ALPHA   = 0.05   # param must beat B&H by at least 5% avg across OOS folds

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
    """
    Run walk-forward sweep.
    Returns (appearances dict, oos_records list, skipped list).

    A fold lands in `skipped` (not silently dropped) when either every combo
    fails to even run on the training data, or every combo runs but none
    satisfies the risk constraints — the latter happens permanently for any
    ticker whose expanding training window has crossed a drawdown beyond
    MAX_DRAWDOWN_LIMIT, since max_dd is measured over the whole window.
    """
    appearances = defaultdict(int)
    oos_records = []
    skipped     = []

    for train, oos, test_year in folds:
        fold_label = f"{test_year} OOS  (train: {TRAIN_START[:4]}–{test_year-1})"

        results = [m for p in combos if (m := _run_params(train, p, signals))]
        if not results:
            skipped.append({
                "test_year": test_year,
                "fold":      fold_label,
                "reason":    "training run failed for every param combo (data or signal error)",
            })
            continue

        df = pd.DataFrame(results)
        passing = df[
            (df["max_dd"] >= config.MAX_DRAWDOWN_LIMIT) &
            (df["margin_calls"] <= config.MAX_MARGIN_CALLS)
        ].sort_values("cagr", ascending=False).head(TOP_N)

        if passing.empty:
            best_dd = df["max_dd"].max()
            skipped.append({
                "test_year": test_year,
                "fold":      fold_label,
                "reason":    (f"no combo passed constraints on training data "
                              f"(best max_dd {best_dd:.1%}, needs ≥ "
                              f"{config.MAX_DRAWDOWN_LIMIT:.0%})"),
            })
            continue

        for _, row in passing.iterrows():
            key = tuple(sorted(row["params"].items()))
            appearances[key] += 1

        bah = _bah(oos)
        for _, row in passing.iterrows():
            m = _run_params(oos, row["params"], signals)
            if m:
                oos_records.append({
                    "test_year": test_year,
                    "fold":     fold_label,
                    "label":    _param_label(row["params"], signals),
                    "params":   row["params"],
                    **{f"oos_{k}": v for k, v in m.items() if k != "params"},
                    "bah_cagr": bah["cagr"],
                })

    return appearances, oos_records, skipped


def _print_oos_table(oos_df, appearances, n_folds, signals, skipped=()):
    w = max(len(_param_label(p, signals)) for p in
            [{k: v for k, v in key} for key in appearances] or [{}]) + 2
    w = max(w, 14)

    print(f"\n  Per-fold OOS results:")
    print(f"  {'Fold':<32} {'Params':<{w}} {'CAGR':>7} {'MaxDD':>7} "
          f"{'vs B&H':>8} {'Pass?':>6}")
    print(f"  {'-'*32} {'-'*w} {'-'*7} {'-'*7} {'-'*8} {'-'*6}")

    rows = [(r["test_year"], r["fold"], "data", r) for _, r in oos_df.iterrows()]
    rows += [(s["test_year"], s["fold"], "skipped", s) for s in skipped]
    rows.sort(key=lambda x: (x[0], x[1]))

    for _, fold_label, kind, r in rows:
        if kind == "skipped":
            print(f"  {fold_label:<32} SKIPPED — {r['reason']}")
            continue
        passes = (r["oos_max_dd"] >= config.MAX_DRAWDOWN_LIMIT and
                  r["oos_margin_calls"] <= config.MAX_MARGIN_CALLS)
        diff = r["oos_cagr"] - r["bah_cagr"]
        print(f"  {r['fold']:<32} {r['label']:<{w}}  "
              f"{r['oos_cagr']:>6.1%}  {r['oos_max_dd']:>6.1%}  "
              f"{diff:>+7.1%}  {'YES' if passes else 'NO':>6}")

    if skipped:
        print(f"\n  {len(skipped)}/{n_folds} folds skipped entirely — no param combo "
              f"satisfied the risk constraints on that fold's training data.")

    print(f"\n  Consistency (appearances in top {TOP_N} across {n_folds} folds):")
    print(f"  {'Params':<{w}} {'Count':>6} {'Avg CAGR':>10} "
          f"{'Avg MaxDD':>10} {'Avg vs B&H':>12}")
    print(f"  {'-'*w} {'-'*6} {'-'*10} {'-'*10} {'-'*12}")

    def _avg_vs_bah(key):
        params = {k: v for k, v in key}
        sub = oos_df[oos_df["params"].apply(lambda p: p == params)]
        return (sub["oos_cagr"] - sub["bah_cagr"]).mean() if not sub.empty else -999

    ranked_all = sorted(appearances.items(),
                        key=lambda x: (x[1], _avg_vs_bah(x[0])), reverse=True)

    # Filter: must meet minimum avg alpha threshold
    ranked = [(key, count) for key, count in ranked_all
              if _avg_vs_bah(key) >= MIN_AVG_ALPHA]
    excluded = [(key, count) for key, count in ranked_all
                if _avg_vs_bah(key) < MIN_AVG_ALPHA]

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

    if excluded:
        excl_labels = ", ".join(_param_label({k: v for k, v in key}, signals)
                                for key, _ in excluded[:3])
        print(f"\n  (excluded — avg alpha < {MIN_AVG_ALPHA:.0%}: {excl_labels}"
              + (f" + {len(excluded)-3} more" if len(excluded) > 3 else "") + ")")

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

        appearances, oos_records, skipped = _sweep_folds(prices, folds, combos, signals)
        oos_df = pd.DataFrame(oos_records)
        if oos_df.empty:
            if skipped:
                print(f"  No results passed constraints. "
                      f"{len(skipped)}/{len(folds)} folds skipped:")
                for s in sorted(skipped, key=lambda x: x["test_year"]):
                    print(f"    {s['fold']}: {s['reason']}")
            else:
                print("  No results passed constraints.")
            continue

        ranked = _print_oos_table(oos_df, appearances, len(folds), signals, skipped=skipped)
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

        appearances, opt_records, skipped = _sweep_folds(prices, opt_folds, combos, signals)
        if not appearances:
            if skipped:
                print(f"  No params passed constraints. "
                      f"{len(skipped)}/{len(opt_folds)} folds skipped:")
                for s in sorted(skipped, key=lambda x: x["test_year"]):
                    print(f"    {s['fold']}: {s['reason']}")
            else:
                print("  No params passed constraints.")
            continue

        if skipped:
            print(f"  ({len(skipped)}/{len(opt_folds)} folds skipped — no combo passed "
                  f"constraints on that fold's training data)")
            for s in sorted(skipped, key=lambda x: x["test_year"]):
                print(f"    {s['fold']}: {s['reason']}")

        opt_df = pd.DataFrame(opt_records)

        def _opt_avg_vs_bah(key):
            params = {k: v for k, v in key}
            sub = opt_df[opt_df["params"].apply(lambda p: p == params)]
            return (sub["oos_cagr"] - sub["bah_cagr"]).mean() if not sub.empty else -999

        ranked_all  = sorted(appearances.items(),
                             key=lambda x: (x[1], _opt_avg_vs_bah(x[0])), reverse=True)
        ranked      = [(k, c) for k, c in ranked_all
                       if _opt_avg_vs_bah(k) >= MIN_AVG_ALPHA] or ranked_all
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
        signals = {"ma"}   # default: MA-only (validated for SPMO)

    tickers = [a for a in args
               if not a.startswith("--") and a not in signals
               and "," not in a] or ["SPMO"]

    if final:
        run_final_test(tickers, signals)
    else:
        run(tickers, signals)
