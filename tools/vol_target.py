"""
Volatility-targeted continuous leverage backtest.

Every other strategy in this repo uses discrete leverage (0x/1x/2x) gated by
the trend signal. This tests a genuinely different mechanism: keep the
existing MA-crossover regime gate (bear -> 1x hold, unchanged), but instead
of holding a *fixed* 2x through the whole bull regime, scale leverage
continuously against trailing realized volatility:

    leverage = clip(target_vol / realized_vol, floor, cap)

This doesn't try to predict direction (that's still the MA signal's job,
unchanged) -- it risk-manages an already-confirmed trend, in the spirit of
volatility-managed-portfolios research (Moreira & Muir). See
research/open_questions.md #15 for the full scope and rationale, and
research/methodology.md before interpreting any "alpha" here.

Walk-forward OOS param selection follows the same discipline as
tools.optimize: for each test year, pick the (window, target_vol, floor, cap)
combo with the best training Sharpe subject to the -50% MaxDD / 0 margin-call
constraints, then evaluate OOS on that year.

FLOOR_GRID includes 1.0 (the original "never delever below 1x in a confirmed
bull regime" rule from research/methodology.md) alongside lower floors
(0.5, 0.0) that let leverage scale *below* 1x -- even to cash -- during a
vol spike, without waiting for the trend signal itself to flip bearish.
This is the mechanism Barroso & Santa-Clara credit for momentum's
crash-risk reduction (see research/strategy_experiments.md's 2026-07-09
entry): the first vol-targeting test only capped upside and floored at 1x,
which structurally ruled out exactly this effect. Keeping floor=1.0 in the
grid as a control isolates whether relaxing it specifically helps, rather
than changing several things at once.

Two comparisons matter, and they ask different questions:
  1. vs Buy & Hold        -- informational, same as every other tool here.
  2. vs matched-average-leverage baseline -- the real test. A vol-targeting
     strategy that simply runs at a lower average leverage than a fixed 2x
     will look "safer" for free -- that's not evidence vol-scaling helps, it's
     just less leverage (the same fairness bug class caught in
     tools/sector_rotation.py, see docs/agents/LESSONS.md 2026-07-06). The
     baseline here is strategies.momentum at a FIXED leverage equal to the
     vol-targeting strategy's own realized average leverage over the same
     fold, so both sides carry identical average exposure.

Significance test: a circular-shift of the regime *signal* would test "does
the trend timing predict direction" -- already answered elsewhere
(tools.significance) and unchanged here. The actual new question is whether
vol-scaled leverage should be assigned to specific (low-vol) days rather than
distributed arbitrarily across the same bull days. So the null here permutes
the realized leverage values *among bull-regime days only* (bear days stay
fixed at 1x), preserving the exact set of leverage values and the exact set
of bull days -- i.e. identical average exposure and identical regime
structure, only WHICH bull day gets WHICH leverage value is randomized.

Usage:
  python -m tools.vol_target                      # SPMO, GLD (live legs)
  python -m tools.vol_target SPMO
  python -m tools.vol_target GLD --significance
"""

import sys
from collections import defaultdict

import numpy as np
import pandas as pd

from core import config
from core.data import fetch
from core.metrics import calc
from core.simulator import run as simulate
from core.portfolio_config import PORTFOLIO, resolve_signal_params
import signals.ma as sig_ma
from strategies import momentum, vol_target

FIRST_TEST_YEAR = 2018

WINDOW_GRID = [10, 20, 63]
TARGET_VOL_GRID = [0.15, 0.20, 0.25, 0.30]
CAP_GRID = [2.0, 2.5, 3.0]
FLOOR_GRID = [0.0, 0.5, 1.0]   # 1.0 = original "never below 1x" rule; 0.0/0.5 test crash de-risking

# Folds where realized vol actually spiked hard -- the sharpest test of whether
# a relaxed floor's crash de-risking shows up, since it's a no-op in calm years.
CRASH_YEARS = {2020, 2022}


def _grid():
    return [{"window": w, "target_vol": tv, "cap": c, "floor": f}
            for w in WINDOW_GRID for tv in TARGET_VOL_GRID
            for c in CAP_GRID for f in FLOOR_GRID]


def _param_label(params):
    return (f"win{params['window']} tgt{params['target_vol']:.0%} "
            f"floor{params['floor']:.1f}x cap{params['cap']:.1f}x")


def _run_params(prices, ma_params, vt_params):
    try:
        signal = sig_ma.signal(prices, ma_params["ma_fast"], ma_params["ma_slow"])
        if len(signal) < 20:
            return None
        pos = vol_target.positions(prices, signal, target_vol=vt_params["target_vol"],
                                    window=vt_params["window"], floor=vt_params["floor"],
                                    cap=vt_params["cap"])
        if len(pos) < 20:
            return None
        result = simulate(prices, pos)
        m = calc(result["equity"])
        m["margin_calls"] = result["margin_calls"]
        m["total_fees"] = result["total_fees"]
        m["avg_leverage"] = float(pos.mean())
        m["params"] = vt_params
        return m
    except Exception:
        return None


def _matched_baseline(prices, ma_params, avg_leverage):
    """Fixed-leverage momentum strategy at the SAME average leverage as the
    vol-targeting run it's being compared to -- isolates "does scaling by vol
    help" from "did this just run at lower average leverage"."""
    signal = sig_ma.signal(prices, ma_params["ma_fast"], ma_params["ma_slow"])
    pos = momentum.positions(signal, leverage=avg_leverage, no_signal_leverage=1.0)
    result = simulate(prices, pos)
    m = calc(result["equity"])
    m["margin_calls"] = result["margin_calls"]
    m["total_fees"] = result["total_fees"]
    return m


def _bah(prices):
    return calc(config.INITIAL_CAPITAL * (prices / prices.iloc[0]))


def _build_folds(prices, ma_params, first_test_year=FIRST_TEST_YEAR, last_year=None):
    folds = []
    current_year = last_year or pd.Timestamp.now().year
    min_train = ma_params["ma_slow"] + 30
    for test_year in range(first_test_year, current_year + 1):
        train = prices[prices.index <= f"{test_year - 1}-12-31"]
        oos = prices[(prices.index >= f"{test_year}-01-01") &
                     (prices.index <= f"{test_year}-12-31")]
        if len(train) < min_train or len(oos) < 20:
            continue
        folds.append((train, oos, test_year))
    return folds


def walk_forward(ticker):
    prices = fetch(ticker)
    ma_params = resolve_signal_params(ticker)
    combos = _grid()
    folds = _build_folds(prices, ma_params)

    fold_records = []
    appearances = defaultdict(int)

    for train, oos, test_year in folds:
        results = [m for p in combos if (m := _run_params(train, ma_params, p))]
        passing = [m for m in results
                   if m["max_dd"] >= config.MAX_DRAWDOWN_LIMIT
                   and m["margin_calls"] <= config.MAX_MARGIN_CALLS]
        if not passing:
            fold_records.append({"test_year": test_year, "skipped": True,
                                  "reason": "no combo passed constraints on training data"})
            continue

        best = max(passing, key=lambda m: m["sharpe"])
        key = tuple(sorted(best["params"].items()))
        appearances[key] += 1

        oos_m = _run_params(oos, ma_params, best["params"])
        if oos_m is None:
            fold_records.append({"test_year": test_year, "skipped": True,
                                  "reason": "selected params produced no valid OOS result"})
            continue

        baseline_m = _matched_baseline(oos, ma_params, oos_m["avg_leverage"])
        bah = _bah(oos)

        fold_records.append({
            "test_year": test_year, "skipped": False, "params": best["params"],
            "avg_leverage": oos_m["avg_leverage"],
            "vt_cagr": oos_m["cagr"], "vt_sharpe": oos_m["sharpe"], "vt_max_dd": oos_m["max_dd"],
            "base_cagr": baseline_m["cagr"], "base_sharpe": baseline_m["sharpe"],
            "base_max_dd": baseline_m["max_dd"],
            "bah_cagr": bah["cagr"],
        })

    return fold_records, appearances


def analyze(ticker):
    print(f"\n{'='*92}")
    print(f"  {ticker} — volatility-targeted leverage (walk-forward)")
    print(f"{'='*92}")

    fold_records, appearances = walk_forward(ticker)
    if not fold_records:
        print("  Not enough data for a walk-forward fit.")
        return None

    print(f"\n  {'Fold':<6} {'Params':<28} {'AvgLev':>7} {'VT Sharpe':>10} "
          f"{'Base Sharpe':>12} {'VT MaxDD':>9} {'Base MaxDD':>11} {'vs B&H':>8}")
    print(f"  {'-'*96}")
    sharpe_deltas, vs_bah = [], []
    crash_fold_records = []
    for f in fold_records:
        if f.get("skipped"):
            print(f"  {f['test_year']:<6} SKIPPED — {f['reason']}")
            continue
        delta = f["vt_sharpe"] - f["base_sharpe"]
        sharpe_deltas.append(delta)
        vs_bah.append(f["vt_cagr"] - f["bah_cagr"])
        if f["test_year"] in CRASH_YEARS:
            crash_fold_records.append(f)
        print(f"  {f['test_year']:<6} {_param_label(f['params']):<28} "
              f"{f['avg_leverage']:>6.2f}x {f['vt_sharpe']:>10.2f} {f['base_sharpe']:>12.2f} "
              f"{f['vt_max_dd']:>9.1%} {f['base_max_dd']:>11.1%} {vs_bah[-1]:>+7.1%}")

    if sharpe_deltas:
        print(f"\n  Avg Sharpe (vol-target minus matched-average-leverage baseline): "
              f"{sum(sharpe_deltas)/len(sharpe_deltas):+.2f}")
        print(f"  Avg vs Buy & Hold CAGR: {sum(vs_bah)/len(vs_bah):+.1%}")
        print(f"  OOS folds: {len(sharpe_deltas)}/{len(fold_records)}")

    if crash_fold_records:
        print(f"\n  Crash-year detail ({', '.join(str(f['test_year']) for f in crash_fold_records)}"
              f") — the specific test of whether a relaxed floor de-risks during vol spikes:")
        for f in crash_fold_records:
            dd_improvement = f["base_max_dd"] - f["vt_max_dd"]
            print(f"    {f['test_year']}: {_param_label(f['params'])}  "
                  f"AvgLev {f['avg_leverage']:.2f}x  VT MaxDD {f['vt_max_dd']:.1%}  "
                  f"vs Base MaxDD {f['base_max_dd']:.1%}  (shallower by {dd_improvement:+.1%})")

    print(f"\n  Param consistency (appearances across folds):")
    for key, count in sorted(appearances.items(), key=lambda x: -x[1]):
        print(f"    {_param_label(dict(key))}: {count} folds")

    return {"fold_records": fold_records, "appearances": appearances}


# ---------------------------------------------------------------------------
# Significance test: permute vol-scaled leverage across bull-regime days only
# ---------------------------------------------------------------------------

def _best_full_period_params(prices, ma_params):
    results = [m for p in _grid() if (m := _run_params(prices, ma_params, p))]
    passing = [m for m in results
               if m["max_dd"] >= config.MAX_DRAWDOWN_LIMIT
               and m["margin_calls"] <= config.MAX_MARGIN_CALLS]
    pool = passing or results
    if not pool:
        return None
    return max(pool, key=lambda m: m["sharpe"])["params"]


def _permute_bull_leverage(pos: pd.Series, signal: pd.Series, rng) -> pd.Series:
    """Randomly reassign the realized leverage values among bull-regime days,
    keeping bear-regime days fixed. Same set of leverage values, same set of
    bull days, same average exposure -- only which day gets which value is
    randomized. Tests whether aligning high leverage with low-vol days
    specifically beats an arbitrary assignment."""
    sig = signal.reindex(pos.index)
    bull_mask = (sig == 1).values
    bull_values = pos.values[bull_mask].copy()
    rng.shuffle(bull_values)
    shuffled = pos.values.copy()
    shuffled[bull_mask] = bull_values
    return pd.Series(shuffled, index=pos.index)


def significance_test(ticker, params=None, n_shifts=1000, seed=42):
    prices = fetch(ticker)
    ma_params = resolve_signal_params(ticker)
    params = params or _best_full_period_params(prices, ma_params)
    if params is None:
        return None

    signal = sig_ma.signal(prices, ma_params["ma_fast"], ma_params["ma_slow"])
    pos = vol_target.positions(prices, signal, target_vol=params["target_vol"],
                                window=params["window"], floor=params["floor"],
                                cap=params["cap"])
    actual_result = simulate(prices, pos)
    actual = calc(actual_result["equity"])

    rng = np.random.default_rng(seed)
    random_cagrs = np.empty(n_shifts)
    random_sharpes = np.empty(n_shifts)
    for i in range(n_shifts):
        shuffled_pos = _permute_bull_leverage(pos, signal, rng)
        result = simulate(prices, shuffled_pos)
        m = calc(result["equity"])
        random_cagrs[i] = m["cagr"]
        random_sharpes[i] = m["sharpe"]

    return {
        "ticker": ticker, "ma_params": ma_params, "params": params,
        "avg_leverage": float(pos.mean()),
        "actual_cagr": actual["cagr"], "actual_sharpe": actual["sharpe"],
        "random_cagrs": random_cagrs, "random_sharpes": random_sharpes,
        "p_cagr": float((random_cagrs >= actual["cagr"]).mean()),
        "p_sharpe": float((random_sharpes >= actual["sharpe"]).mean()),
    }


def _verdict(p):
    if p < 0.05:
        return "SIGNIFICANT"
    if p < 0.10:
        return "borderline"
    return "NOT significant — indistinguishable from random assignment of the same leverage values"


def _print_significance(ticker, n_shifts=1000):
    r = significance_test(ticker, n_shifts=n_shifts)
    if r is None:
        print(f"\n  {ticker}: not enough data for a significance test.")
        return
    print(f"\n  Significance test ({_param_label(r['params'])}, avg leverage "
          f"{r['avg_leverage']:.2f}x, {n_shifts:,} bull-day permutations):")
    print(f"    Actual CAGR {r['actual_cagr']:.1%} vs random-assignment median "
          f"{np.median(r['random_cagrs']):.1%}   p={r['p_cagr']:.3f}   {_verdict(r['p_cagr'])}")
    print(f"    Actual Sharpe {r['actual_sharpe']:.2f} vs random-assignment median "
          f"{np.median(r['random_sharpes']):.2f}   p={r['p_sharpe']:.3f}   {_verdict(r['p_sharpe'])}")


if __name__ == "__main__":
    args = sys.argv[1:]
    show_sig = "--significance" in args
    args = [a for a in args if a != "--significance"]

    tickers = [a.upper() for a in args] or list(PORTFOLIO)
    for t in tickers:
        analyze(t)
        if show_sig:
            _print_significance(t)
