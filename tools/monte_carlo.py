"""
Monte Carlo forward simulation: what could happen, not just what did.

tools/options_bootstrap.py resamples the *exact* 9-13 historical regimes -- it
can only ever produce recombinations of what actually happened. It can't
imagine a bear market worse than 2022, or a whipsaw stretch worse than Feb
2022, because it's bounded by the historical sample. This tool instead
calibrates a return-generating model to the historical data and simulates
thousands of *synthetic* forward price paths, running the actual signal +
leverage logic against each one.

Two calibration methods, run side by side as an honest model-risk check:
  - GBM: i.i.d. daily log-returns drawn from a Normal(mu, sigma) fit to
    history. Simple, transparent, but has no fat tails or trend persistence.
  - Block bootstrap: resamples overlapping blocks of real historical daily
    log-returns. Preserves fat tails and autocorrelation/trend persistence
    without assuming a parametric distribution, at the cost of only ever
    recombining historical block-level behavior (a middle ground between
    the regime-level bootstrap and pure GBM).

Each synthetic path is prefixed with enough real historical data to warm up
the MA windows, then only the simulated forward segment is scored.

Usage:
  python -m tools.monte_carlo              # all portfolio tickers, 5yr horizon
  python -m tools.monte_carlo SPMO
  python -m tools.monte_carlo SMH --horizon 10 --resamples 2000
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

HORIZON_YEARS = 5
N_SIMS = 500
BLOCK_LEN = 21   # ~1 trading month, matches the realized-vol window used elsewhere


def _calibrate(log_rets: pd.Series) -> tuple[float, float]:
    return float(log_rets.mean()), float(log_rets.std())


def _gbm_path(mu, sigma, n_days, rng):
    return rng.normal(mu, sigma, n_days)


def _block_bootstrap_path(log_rets, n_days, block_len, rng):
    arr = log_rets.values
    n_blocks = n_days // block_len + 1
    starts = rng.integers(0, len(arr) - block_len, n_blocks)
    return np.concatenate([arr[s:s + block_len] for s in starts])[:n_days]


def forward_sim(ticker: str, horizon_years: float = HORIZON_YEARS,
                n_sims: int = N_SIMS, seed: int = 42):
    prices = fetch(ticker)
    cfg = resolve_signal_params(ticker)
    ma_slow = cfg["ma_slow"]
    log_rets = np.log(prices / prices.shift(1)).dropna()
    mu, sigma = _calibrate(log_rets)

    n_days = int(horizon_years * 252)
    # real tail history, just enough to warm up the slow MA before the
    # simulated segment starts
    burn_in = prices.iloc[-(ma_slow + 5):]
    last_log_price = np.log(burn_in.iloc[-1])

    rng = np.random.default_rng(seed)
    results = {"gbm": [], "block": []}

    for method in ("gbm", "block"):
        for _ in range(n_sims):
            fwd_log_rets = (_gbm_path(mu, sigma, n_days, rng) if method == "gbm"
                           else _block_bootstrap_path(log_rets, n_days, BLOCK_LEN, rng))
            fwd_log_prices = last_log_price + np.cumsum(fwd_log_rets)
            fwd_prices = np.exp(fwd_log_prices)
            fwd_index = pd.bdate_range(burn_in.index[-1] + pd.Timedelta(days=1), periods=n_days)
            full_prices = pd.concat([burn_in.iloc[:-1],
                                     pd.Series(fwd_prices, index=fwd_index)])
            full_prices.index = pd.bdate_range(burn_in.index[0], periods=len(full_prices))

            signal = sig_ma.signal(full_prices, cfg["ma_fast"], cfg["ma_slow"])
            pos = momentum.positions(signal)
            result = simulate(full_prices, pos)
            fwd_equity = result["equity"].iloc[-n_days:]
            m = calc(fwd_equity / fwd_equity.iloc[0] * 100_000)
            results[method].append({"cagr": m["cagr"], "max_dd": m["max_dd"], "total": m["total"]})

    return {"ticker": ticker, "cfg": cfg, "mu": mu, "sigma": sigma,
            "n_days": n_days, "results": results}


def _summarize(rows):
    cagrs = np.array([r["cagr"] for r in rows])
    dds = np.array([r["max_dd"] for r in rows])
    totals = np.array([r["total"] for r in rows])
    return {
        "cagr_median": float(np.median(cagrs)),
        "cagr_p5": float(np.percentile(cagrs, 5)),
        "cagr_p95": float(np.percentile(cagrs, 95)),
        "dd_median": float(np.median(dds)),
        "dd_p5": float(np.percentile(dds, 5)),   # worst 5% of paths
        "total_median": float(np.median(totals)),
        "p_loss": float((cagrs < 0).mean()),
    }


def analyze(ticker: str, horizon_years: float = HORIZON_YEARS, n_sims: int = N_SIMS):
    r = forward_sim(ticker, horizon_years=horizon_years, n_sims=n_sims)
    cfg = r["cfg"]

    print(f"\n{'='*76}")
    print(f"  {ticker} MA{cfg['ma_fast']}/{cfg['ma_slow']} — Monte Carlo forward simulation "
          f"({horizon_years:.0f}yr horizon, {n_sims:,} sims/method)")
    print(f"{'='*76}")
    print(f"  Calibrated from history: daily mu {r['mu']:.5f}, sigma {r['sigma']:.5f}  "
          f"(annualized ~{r['mu']*252:.1%} drift, {r['sigma']*np.sqrt(252):.1%} vol)")

    for method, label in [("gbm", "GBM (i.i.d. Normal draws)"),
                          ("block", "Block bootstrap (real return blocks)")]:
        s = _summarize(r["results"][method])
        print(f"\n  {label}:")
        print(f"    CAGR      median {s['cagr_median']:+.1%}   "
              f"5-95pct [{s['cagr_p5']:+.1%}, {s['cagr_p95']:+.1%}]")
        print(f"    MaxDD     median {s['dd_median']:.1%}   worst-5pct {s['dd_p5']:.1%}")
        print(f"    P(losing money over {horizon_years:.0f}yr): {s['p_loss']:.0%}")

    gbm_s, block_s = _summarize(r["results"]["gbm"]), _summarize(r["results"]["block"])
    agree = abs(gbm_s["cagr_median"] - block_s["cagr_median"]) < 0.05
    print(f"\n  Model agreement: {'GBM and block bootstrap broadly agree' if agree else 'GBM and block bootstrap DIVERGE — treat either alone with caution'}"
          f"  (median CAGR gap {abs(gbm_s['cagr_median']-block_s['cagr_median']):.1%})")
    print(f"  Note: GBM assumes i.i.d. Normal daily returns (no fat tails, no trend")
    print(f"  persistence); block bootstrap preserves both from real history but can only")
    print(f"  recombine historical block-level behavior. Neither is \"the answer\" alone.")


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
