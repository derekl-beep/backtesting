"""
RSI-band mean-reversion backtest for the macro/commodity/international ETFs
already rejected under MA-crossover momentum (see research/etf_candidates.md:
EWJ, EEM, TLT, GDX, SLV, DBC, VNQ, HYG, FXI, EWZ all showed near-zero or
negative alpha at MA50/100). Roadmap hypothesis: these don't trend cleanly
enough for a momentum signal, but a contrarian RSI-band entry/exit might
capture their moves instead. Deliberately 1x-in-trade/0x-cash (no margin) --
mean-reversion is a lower-conviction, shorter-duration trade than trend-
following, so it doesn't carry this project's usual 2x leverage overlay.

Walk-forward OOS param selection follows the same discipline as
tools.optimize: for each test year, pick the (oversold, overbought) band
with the best Sharpe using only data through the prior year-end, then
evaluate OOS on that year. No margin/drawdown constraint gate is applied
(there's no leverage to blow through it), but MaxDD is still reported.

A circular-shift significance test (same methodology as tools.significance,
reimplemented here for the RSI-band signal since that tool is hardcoded to
MA-crossover + momentum.positions) checks whether any OOS-positive candidate
is actually distinguishable from random timing of the same in-trade exposure,
not just a favorable point estimate.

Usage:
  python -m tools.mean_reversion                     # all 10 rejected candidates
  python -m tools.mean_reversion EWJ EEM
  python -m tools.mean_reversion TLT --period 21
  python -m tools.mean_reversion FXI --significance   # + circular-shift test
"""

import sys
from collections import defaultdict

import numpy as np
import pandas as pd

from core.data import fetch
from core.metrics import calc
from core.simulator import run as simulate
import signals.rsi_band as sig_rsi_band
from strategies import mean_reversion

CANDIDATES = ["EWJ", "EEM", "TLT", "GDX", "SLV", "DBC", "VNQ", "HYG", "FXI", "EWZ"]

RSI_PERIOD = 14
OVERSOLD_LEVELS = [20, 25, 30, 35]
OVERBOUGHT_LEVELS = [65, 70, 75, 80]
FIRST_TEST_YEAR = 2018
MIN_TRAIN_OBS = 300


def _grid(period=RSI_PERIOD):
    return [{"period": period, "oversold": o, "overbought": b}
           for o in OVERSOLD_LEVELS for b in OVERBOUGHT_LEVELS]


def _run_params(prices, params):
    try:
        sig = sig_rsi_band.signal(prices, params["period"], params["oversold"],
                                  params["overbought"])
        if len(sig) < 20:
            return None
        pos = mean_reversion.positions(sig)
        result = simulate(prices, pos)
        m = calc(result["equity"])
        m["total_fees"] = result["total_fees"]
        m["n_trades"] = int((pos.diff() != 0).sum())
        m["params"] = params
        return m
    except Exception:
        return None


def _bah(prices):
    from core.config import INITIAL_CAPITAL
    return calc(INITIAL_CAPITAL * (prices / prices.iloc[0]))


def _build_folds(prices, first_test_year=FIRST_TEST_YEAR, last_year=None):
    folds = []
    current_year = last_year or pd.Timestamp.now().year
    for test_year in range(first_test_year, current_year + 1):
        train = prices[prices.index <= f"{test_year - 1}-12-31"]
        oos = prices[(prices.index >= f"{test_year}-01-01") &
                    (prices.index <= f"{test_year}-12-31")]
        if len(train) < MIN_TRAIN_OBS or len(oos) < 20:
            continue
        folds.append((train, oos, test_year))
    return folds


def walk_forward(ticker, period=RSI_PERIOD):
    prices = fetch(ticker)
    combos = _grid(period)
    folds = _build_folds(prices)

    fold_records = []
    appearances = defaultdict(int)

    for train, oos, test_year in folds:
        results = [m for p in combos if (m := _run_params(train, p))]
        if not results:
            fold_records.append({"test_year": test_year, "skipped": True,
                                 "reason": "no combo produced a valid signal on training data"})
            continue

        best = max(results, key=lambda m: m["sharpe"])
        key = tuple(sorted(best["params"].items()))
        appearances[key] += 1

        oos_m = _run_params(oos, best["params"])
        if oos_m is None:
            fold_records.append({"test_year": test_year, "skipped": True,
                                 "reason": "selected params produced no valid OOS signal"})
            continue

        bah = _bah(oos)
        fold_records.append({
            "test_year": test_year, "skipped": False, "params": best["params"],
            "oos_cagr": oos_m["cagr"], "oos_sharpe": oos_m["sharpe"],
            "oos_max_dd": oos_m["max_dd"], "oos_trades": oos_m["n_trades"],
            "bah_cagr": bah["cagr"],
        })

    return fold_records, appearances


def _param_label(params):
    return f"RSI{params['period']} {params['oversold']}/{params['overbought']}"


def analyze(ticker, period=RSI_PERIOD):
    print(f"\n{'='*78}")
    print(f"  {ticker} — RSI-band mean reversion (walk-forward)")
    print(f"{'='*78}")

    fold_records, appearances = walk_forward(ticker, period)
    if not fold_records:
        print("  Not enough data for a walk-forward fit.")
        return

    print(f"\n  {'Fold':<8} {'Params':<16} {'OOS CAGR':>9} {'OOS Sharpe':>11} "
          f"{'OOS MaxDD':>10} {'Trades':>7} {'vs B&H':>8}")
    print(f"  {'-'*72}")
    avg_vs_bah = []
    for f in fold_records:
        if f.get("skipped"):
            print(f"  {f['test_year']:<8} SKIPPED — {f['reason']}")
            continue
        vs = f["oos_cagr"] - f["bah_cagr"]
        avg_vs_bah.append(vs)
        print(f"  {f['test_year']:<8} {_param_label(f['params']):<16} "
              f"{f['oos_cagr']:>9.1%} {f['oos_sharpe']:>11.2f} {f['oos_max_dd']:>10.1%} "
              f"{f['oos_trades']:>7} {vs:>+7.1%}")

    if avg_vs_bah:
        print(f"\n  Avg OOS vs B&H: {sum(avg_vs_bah)/len(avg_vs_bah):+.1%}")
        print(f"  OOS folds: {len(avg_vs_bah)}/{len(fold_records)}")

    print(f"\n  Param consistency (appearances across folds):")
    for key, count in sorted(appearances.items(), key=lambda x: -x[1]):
        params = dict(key)
        print(f"    {_param_label(params)}: {count} folds")

    return {"fold_records": fold_records, "appearances": appearances}


# ---------------------------------------------------------------------------
# Significance test: circular shift, same methodology as tools.significance
# ---------------------------------------------------------------------------

def _best_full_period_params(prices, period=RSI_PERIOD):
    """Fit (oversold, overbought) once on the full history by Sharpe -- the
    RSI-band analog of tools.significance using an already-decided param
    set (resolve_signal_params) rather than re-optimizing inside the test."""
    results = [m for p in _grid(period) if (m := _run_params(prices, p))]
    if not results:
        return None
    return max(results, key=lambda m: m["sharpe"])["params"]


def significance_test(ticker, period=RSI_PERIOD, n_shifts=1000, seed=42,
                      params=None):
    prices = fetch(ticker)
    params = params or _best_full_period_params(prices, period)
    if params is None:
        return None

    signal = sig_rsi_band.signal(prices, params["period"], params["oversold"],
                                 params["overbought"])
    actual_result = simulate(prices, mean_reversion.positions(signal))
    actual = calc(actual_result["equity"])

    n = len(signal)
    rng = np.random.default_rng(seed)
    random_cagrs = np.empty(n_shifts)
    random_sharpes = np.empty(n_shifts)
    sig_vals = signal.values
    for i in range(n_shifts):
        shift = rng.integers(1, n)
        shifted = pd.Series(np.roll(sig_vals, shift), index=signal.index)
        result = simulate(prices, mean_reversion.positions(shifted))
        m = calc(result["equity"])
        random_cagrs[i] = m["cagr"]
        random_sharpes[i] = m["sharpe"]

    return {
        "ticker": ticker, "params": params,
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
    return "NOT significant — indistinguishable from random timing of the same exposure"


def _print_significance(ticker, period=RSI_PERIOD, n_shifts=1000):
    r = significance_test(ticker, period=period, n_shifts=n_shifts)
    if r is None:
        print(f"\n  {ticker}: not enough data for a significance test.")
        return
    print(f"\n  Significance test ({_param_label(r['params'])}, {n_shifts:,} circular shifts):")
    print(f"    Actual CAGR {r['actual_cagr']:.1%} vs random-timing median "
          f"{np.median(r['random_cagrs']):.1%}   p={r['p_cagr']:.3f}   {_verdict(r['p_cagr'])}")
    print(f"    Actual Sharpe {r['actual_sharpe']:.2f} vs random-timing median "
          f"{np.median(r['random_sharpes']):.2f}   p={r['p_sharpe']:.3f}   {_verdict(r['p_sharpe'])}")


if __name__ == "__main__":
    args = sys.argv[1:]
    period = RSI_PERIOD
    show_sig = "--significance" in args
    args = [a for a in args if a != "--significance"]
    if "--period" in args:
        idx = args.index("--period")
        period = int(args[idx + 1])
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    tickers = [a.upper() for a in args] or CANDIDATES
    for t in tickers:
        analyze(t, period=period)
        if show_sig:
            _print_significance(t, period=period)
