"""
Statistical significance of the MA-crossover's TIMING, via a circular-shift
permutation test.

Every finding in this project's research log compares the actual strategy's
performance against buy-and-hold or against itself at different params. None
of it asks the more fundamental question: does the specific timing chosen by
the MA crossover beat *random* timing of the same amount of leverage exposure,
or could the historical numbers be explained by luck plus a rising market?

Method: circularly shift the signal series (rotate the whole 0/1 regime
pattern by a random number of days, wrapping around) many times. This
preserves the exact regime-block-length distribution and total time spent
levered -- only WHEN those blocks land on the calendar is randomized. Run the
same leverage strategy against each shifted signal and compare the actual
strategy's CAGR/Sharpe to the resulting distribution. The fraction of random
shifts that do at least as well as the actual timing is the p-value.

This is a weaker (more generous) null than "pure noise" -- it only asks
whether *this specific timing choice* beats *other timing of the same
block structure*, not whether leverage itself helps. See RESEARCH.md's
"Methodology" entry for that broader finding.

Usage:
  python -m tools.significance              # all portfolio tickers
  python -m tools.significance SPMO
  python -m tools.significance SMH --resamples 5000
"""

import sys

import numpy as np
import pandas as pd

from core.data import fetch
from core.metrics import calc
from core.simulator import run as simulate
from core.portfolio_config import PORTFOLIO, resolve_signal_params
import signals.ma as sig_ma
from strategies import momentum

N_SHIFTS = 1000


def circular_shift_test(ticker: str, n_shifts: int = N_SHIFTS, seed: int = 42):
    prices = fetch(ticker)
    cfg = resolve_signal_params(ticker)
    signal = sig_ma.signal(prices, cfg["ma_fast"], cfg["ma_slow"])

    actual_result = simulate(prices, momentum.positions(signal))
    actual = calc(actual_result["equity"])

    n = len(signal)
    rng = np.random.default_rng(seed)
    random_cagrs = np.empty(n_shifts)
    random_sharpes = np.empty(n_shifts)
    sig_vals = signal.values
    for i in range(n_shifts):
        shift = rng.integers(1, n)
        shifted_signal = pd.Series(np.roll(sig_vals, shift), index=signal.index)
        result = simulate(prices, momentum.positions(shifted_signal))
        m = calc(result["equity"])
        random_cagrs[i] = m["cagr"]
        random_sharpes[i] = m["sharpe"]

    return {
        "ticker": ticker, "cfg": cfg,
        "actual_cagr": actual["cagr"], "actual_sharpe": actual["sharpe"],
        "random_cagrs": random_cagrs, "random_sharpes": random_sharpes,
        "p_cagr": float((random_cagrs >= actual["cagr"]).mean()),
        "p_sharpe": float((random_sharpes >= actual["sharpe"]).mean()),
    }


def _verdict(p: float) -> str:
    if p < 0.05:
        return "SIGNIFICANT (p<0.05) — timing beats random at conventional threshold"
    if p < 0.10:
        return "borderline (p<0.10) — suggestive but not conventionally significant"
    return "NOT significant — indistinguishable from random timing of the same exposure"


def analyze(ticker: str, n_shifts: int = N_SHIFTS):
    r = circular_shift_test(ticker, n_shifts=n_shifts)
    cfg = r["cfg"]

    print(f"\n{'='*72}")
    print(f"  {ticker} MA{cfg['ma_fast']}/{cfg['ma_slow']} — timing significance "
          f"({n_shifts:,} circular shifts)")
    print(f"{'='*72}")
    print(f"  Actual CAGR   : {r['actual_cagr']:>7.1%}   "
          f"(percentile {float((r['random_cagrs'] < r['actual_cagr']).mean()):.0%} "
          f"of random-timing distribution)")
    print(f"  Actual Sharpe : {r['actual_sharpe']:>7.2f}   "
          f"(percentile {float((r['random_sharpes'] < r['actual_sharpe']).mean()):.0%})")
    print(f"\n  Random-timing CAGR:   median {np.median(r['random_cagrs']):.1%}  "
          f"5-95pct [{np.percentile(r['random_cagrs'], 5):.1%}, "
          f"{np.percentile(r['random_cagrs'], 95):.1%}]")
    print(f"  Random-timing Sharpe: median {np.median(r['random_sharpes']):.2f}  "
          f"5-95pct [{np.percentile(r['random_sharpes'], 5):.2f}, "
          f"{np.percentile(r['random_sharpes'], 95):.2f}]")
    print(f"\n  p-value (CAGR, one-sided)  : {r['p_cagr']:.3f}   — {_verdict(r['p_cagr'])}")
    print(f"  p-value (Sharpe, one-sided): {r['p_sharpe']:.3f}   — {_verdict(r['p_sharpe'])}")
    print(f"\n  Note: this null preserves the exact regime-block-length distribution and")
    print(f"  total time levered -- it tests whether THIS timing beats OTHER timing of")
    print(f"  the same exposure, not whether leverage itself helps (see RESEARCH.md).")


if __name__ == "__main__":
    args = sys.argv[1:]
    n_shifts = N_SHIFTS
    if "--resamples" in args:
        idx = args.index("--resamples")
        n_shifts = int(args[idx + 1])
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    tickers = [a.upper() for a in args if not a.startswith("--")] or list(PORTFOLIO)
    for t in tickers:
        analyze(t, n_shifts=n_shifts)
