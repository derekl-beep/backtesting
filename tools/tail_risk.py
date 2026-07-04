"""
Value at Risk (VaR) and Conditional VaR (CVaR / Expected Shortfall).

Every risk metric in this project so far is Sharpe (penalizes upside and
downside volatility symmetrically -- wrong for a strategy built on convex
payoffs) or MaxDD (a single historical data point, not a distribution, and
silent about a future worse than what's already happened). VaR answers
"there's a P% chance of losing more than X"; CVaR goes further: "*given*
we're in that worst P% tail, what's the average loss" -- the metric real
risk desks size capital against, since (unlike VaR) it accounts for the
severity of tail losses, not just where the tail starts.

Two views:
  1. Historical daily VaR/CVaR on the actual deployed strategy's equity
     curve -- backward-looking, cheap, no model assumptions.
  2. Forward-looking VaR/CVaR on tools.monte_carlo's simulated distribution
     (both GBM and block-bootstrap) -- total return over the horizon, and
     max drawdown, at 95% and 99% confidence.

Caveat printed explicitly: 99% tail estimates need far more samples than
95% to be stable (99% of 300 sims is only ~3 observations in the tail) --
this tool defaults to more simulations than tools.monte_carlo for exactly
that reason, and warns when --resamples is still too low for the 99% figure
to be trusted.

Usage:
  python -m tools.tail_risk              # all portfolio tickers
  python -m tools.tail_risk SPMO GLD SMH
  python -m tools.tail_risk SMH --horizon 10 --resamples 2000
"""

import sys

import numpy as np

from core.data import fetch
from core.portfolio_config import PORTFOLIO, resolve_signal_params
import signals.ma as sig_ma
from strategies import momentum
from core.simulator import run as simulate
from tools.monte_carlo import forward_sim, HORIZON_YEARS

N_SIMS = 800
MIN_TAIL_OBS_FOR_STABLE_99 = 20   # need >=20 obs in the 1% tail for a stable estimate


def var_cvar(returns, alpha=0.95):
    """
    returns: array of period returns (negative = loss).
    Returns (VaR, CVaR) as loss magnitudes at the (1-alpha) tail -- positive
    means a real loss at that confidence level, negative means even the
    tail outcome at that confidence level is still a gain.
    """
    sorted_rets = np.sort(returns)
    idx = max(1, int((1 - alpha) * len(sorted_rets)))
    var = -sorted_rets[idx - 1]
    cvar = -sorted_rets[:idx].mean()
    return var, cvar


def historical_daily_var_cvar(ticker: str, alpha: float = 0.95):
    prices = fetch(ticker)
    cfg = resolve_signal_params(ticker)
    signal = sig_ma.signal(prices, cfg["ma_fast"], cfg["ma_slow"])
    result = simulate(prices, momentum.positions(signal))
    daily_rets = result["equity"].pct_change().dropna().values
    return var_cvar(daily_rets, alpha), len(daily_rets)


def _fmt(val):
    return f"{val:+.1%} (gain, not a loss)" if val < 0 else f"{val:.1%}"


def analyze(ticker: str, horizon_years: float = HORIZON_YEARS, n_sims: int = N_SIMS):
    print(f"\n{'='*78}")
    print(f"  {ticker} — tail risk (VaR / CVaR)")
    print(f"{'='*78}")

    print(f"\n  Historical daily VaR/CVaR (backward-looking, {ticker}'s deployed strategy):")
    for alpha in (0.95, 0.99):
        (var, cvar), n_obs = historical_daily_var_cvar(ticker, alpha)
        tail_n = max(1, int((1 - alpha) * n_obs))
        print(f"    {alpha:.0%} confidence: VaR {_fmt(var)}   CVaR {_fmt(cvar)}   "
              f"({tail_n} obs in tail, {n_obs} total days)")

    r = forward_sim(ticker, horizon_years=horizon_years, n_sims=n_sims)
    print(f"\n  Forward-looking VaR/CVaR ({horizon_years:.0f}yr Monte Carlo, {n_sims:,} sims/method):")
    for method, label in [("gbm", "GBM"), ("block", "Block bootstrap")]:
        totals = np.array([row["total"] for row in r["results"][method]])
        dds = np.array([row["max_dd"] for row in r["results"][method]])
        print(f"\n    {label}:")
        for alpha in (0.95, 0.99):
            tail_n = max(1, int((1 - alpha) * n_sims))
            stability_note = ""
            if alpha == 0.99 and tail_n < MIN_TAIL_OBS_FOR_STABLE_99:
                stability_note = (f"  ⚠ only {tail_n} sims in tail — increase "
                                  f"--resamples for a stable 99% estimate")
            var_t, cvar_t = var_cvar(totals, alpha)
            var_d, cvar_d = var_cvar(dds, alpha)
            print(f"      {alpha:.0%}: Total-return VaR {_fmt(var_t)}  CVaR {_fmt(cvar_t)}   "
                  f"|  MaxDD VaR {var_d:.1%}  CVaR {cvar_d:.1%}{stability_note}")

    print(f"\n  VaR = loss threshold at that confidence (\"P% chance of losing more than this\").")
    print(f"  CVaR = average loss *given* you're past that threshold (severity, not just")
    print(f"  frequency) — the more conservative, coherent risk measure of the two.")


if __name__ == "__main__":
    args = sys.argv[1:]
    horizon = HORIZON_YEARS
    n_sims = N_SIMS

    if "--horizon" in args:
        idx = args.index("--horizon")
        horizon = float(args[idx + 1])
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]
    if "--resamples" in args:
        idx = args.index("--resamples")
        n_sims = int(args[idx + 1])
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    tickers = [a.upper() for a in args if not a.startswith("--")] or list(PORTFOLIO)
    for t in tickers:
        analyze(t, horizon_years=horizon, n_sims=n_sims)
