"""
Bootstrap confidence intervals for the call-options overlay's per-regime returns.

Every options-overlay finding so far (win rate, median RoP) is a point estimate from
9-13 historical regimes -- one realized path, not a distribution. This tool resamples
the historical per-regime returns with replacement to answer two different questions:

  1. How much could the *observed* win rate / median RoP have differed just from
     small-sample noise, if the same number of regimes had played out differently?
  2. Looking forward, what's the plausible range of outcomes over the next N regimes
     (compounded capital return, chance of a losing stretch), assuming the future
     draws from the same distribution as the historical regimes?

Usage:
  python -m tools.options_bootstrap                  # default: SPMO signal -> QQQ calls
  python -m tools.options_bootstrap GLD               # GLD signal -> GLD calls
  python -m tools.options_bootstrap SMH --horizon 10  # project 10 future regimes
  python -m tools.options_bootstrap SMH --resamples 20000
"""

import sys

import numpy as np

from core.data import fetch
from core.portfolio_config import PORTFOLIO, DEFAULT_SIGNAL
import signals.ma as sig_ma
from tools.options_backtest import (
    SIGNAL_TICKER, CALL_TICKER, IV_TICKER, ROLL_DTE,
    _get_regimes, simulate_regime_with_rolls,
)
from tools.options_chain_check import iv_proxy_series

CAPITAL      = 100_000
TARGET_DELTA = 0.50
BUDGET_FRAC  = 0.03
N_RESAMPLES  = 10_000
HORIZON      = 5   # future regimes to project


def _regime_rops(ticker: str) -> list[float]:
    """Per-regime return-on-premium for `ticker`'s own signal -> own calls,
    or the shipped SPMO -> QQQ cross-ticker overlay if ticker == SIGNAL_TICKER."""
    if ticker == SIGNAL_TICKER:
        signal_prices = fetch(SIGNAL_TICKER)
        call_prices   = fetch(CALL_TICKER)
        iv_prices     = fetch(IV_TICKER)
        cfg           = PORTFOLIO[SIGNAL_TICKER]
    else:
        signal_prices = fetch(ticker)
        call_prices   = signal_prices
        cfg           = PORTFOLIO.get(ticker, DEFAULT_SIGNAL)
        iv_prices     = iv_proxy_series(ticker, signal_prices)

    signal  = sig_ma.signal(signal_prices, cfg["ma_fast"], cfg["ma_slow"])
    regimes = _get_regimes(signal)

    rops = []
    for start, end in regimes:
        _, agg = simulate_regime_with_rolls(start, end, call_prices, iv_prices,
                                             TARGET_DELTA, BUDGET_FRAC, CAPITAL,
                                             iv_shock=0.0, roll_dte=ROLL_DTE)
        if agg:
            rops.append(agg["return_on_premium"])
    return rops


def _pct(a, p):
    return float(np.percentile(a, p))


def bootstrap(ticker: str, resamples: int = N_RESAMPLES, horizon: int = HORIZON):
    rops = np.array(_regime_rops(ticker))
    n = len(rops)
    if n < 3:
        print(f"\n{ticker}: only {n} historical regimes — too few to bootstrap meaningfully.")
        return

    win_rate      = float((rops > 0).mean())
    median_rop    = float(np.median(rops))
    capital_rets  = BUDGET_FRAC * rops   # sizing.py's own conversion: capital_ret = budget% x RoP

    rng = np.random.default_rng(42)

    # --- Question 1: how much could the observed stats have differed by chance,
    # if we'd drawn the same *number* of historical regimes again? ---
    resample_win_rates   = np.empty(resamples)
    resample_medians     = np.empty(resamples)
    for i in range(resamples):
        draw = rng.choice(rops, size=n, replace=True)
        resample_win_rates[i] = (draw > 0).mean()
        resample_medians[i]   = np.median(draw)

    # --- Question 2: projecting forward `horizon` future regimes ---
    fwd_terminal   = np.empty(resamples)
    fwd_win_rate   = np.empty(resamples)
    fwd_worst      = np.empty(resamples)
    for i in range(resamples):
        draw = rng.choice(capital_rets, size=horizon, replace=True)
        fwd_terminal[i] = np.prod(1 + draw) - 1
        fwd_win_rate[i] = (draw > 0).mean()
        fwd_worst[i]    = draw.min()

    print(f"\n{'='*70}")
    print(f"  {ticker} options overlay — bootstrap over {n} historical regimes")
    print(f"{'='*70}")
    print(f"  Observed: win rate {win_rate:.0%} ({int(win_rate*n)}/{n}), "
          f"median RoP {median_rop:+.0%}")
    print()
    print(f"  Q1: if the SAME {n} regimes had played out differently (resampled "
          f"{resamples:,}x)")
    print(f"      Win rate    90% CI: [{_pct(resample_win_rates, 5):.0%}, "
          f"{_pct(resample_win_rates, 95):.0%}]")
    print(f"      Median RoP  90% CI: [{_pct(resample_medians, 5):+.0%}, "
          f"{_pct(resample_medians, 95):+.0%}]")
    print()
    print(f"  Q2: projecting the NEXT {horizon} regimes (budget {BUDGET_FRAC:.0%}/regime, "
          f"capital compounds)")
    print(f"      Compounded capital return over {horizon} regimes:")
    print(f"        median   {_pct(fwd_terminal, 50):+.0%}")
    print(f"        90% CI:  [{_pct(fwd_terminal, 5):+.0%}, {_pct(fwd_terminal, 95):+.0%}]")
    print(f"      P(losing money over {horizon} regimes)     : "
          f"{float((fwd_terminal < 0).mean()):.0%}")
    print(f"      P(at least one losing regime in the {horizon}): "
          f"{float((fwd_win_rate < 1.0).mean()):.0%}")
    print(f"      Worst single regime in a typical draw (median): "
          f"{_pct(fwd_worst, 50):+.1%} of premium budget")
    print()


if __name__ == "__main__":
    args      = sys.argv[1:]
    resamples = N_RESAMPLES
    horizon   = HORIZON

    if "--resamples" in args:
        idx = args.index("--resamples")
        resamples = int(args[idx + 1])
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]
    if "--horizon" in args:
        idx = args.index("--horizon")
        horizon = int(args[idx + 1])
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    tickers = [a.upper() for a in args if not a.startswith("--")] or [SIGNAL_TICKER]
    for t in tickers:
        bootstrap(t, resamples=resamples, horizon=horizon)
