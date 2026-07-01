"""
Portfolio tuning pipeline — single command to find and apply optimal params.

Runs portfolio-level walk-forward optimization, compares recommended params
vs current, and optionally writes the changes to core/portfolio_config.py.

Usage:
  python -m tools.tune               # optimize and compare, no changes
  python -m tools.tune --apply       # optimize, compare, then apply if better
  python -m tools.tune --dry-run     # same as default (alias)
"""

import sys
import re

import matplotlib
matplotlib.use("Agg")

from tools.portfolio import DEFAULT_PORTFOLIO
from tools.portfolio_optimize import optimize, _combo_label


# ── helpers ──────────────────────────────────────────────────────────────────

def _run_portfolio(portfolio: dict) -> dict:
    """Run a full portfolio backtest and return aggregate metrics."""
    from core import config
    from core.data import fetch
    from core.metrics import calc
    from core.simulator import run as simulate
    from signals import ma as sig_ma
    from strategies import momentum

    prices_dict = {t: fetch(t) for t in portfolio}
    common_idx  = list(prices_dict.values())[0].index
    for p in prices_dict.values():
        common_idx = common_idx.intersection(p.index)

    total_equity = None
    for ticker, cfg in portfolio.items():
        prices = prices_dict[ticker].reindex(common_idx).dropna()
        sig    = sig_ma.signal(prices, cfg["ma_fast"], cfg["ma_slow"])
        pos    = momentum.positions(sig)
        result = simulate(prices, pos, capital=config.INITIAL_CAPITAL * cfg["weight"])
        eq     = result["equity"]
        total_equity = eq if total_equity is None else (
            total_equity + eq).reindex(total_equity.index.intersection(eq.index))

    return calc(total_equity)


def _build_recommended(tickers, ranked) -> dict:
    """Build a portfolio dict from the top-ranked joint combo."""
    best_combo = ranked[0][0]   # tuple of (fast, slow) pairs
    new_portfolio = {}
    for ticker, (fast, slow) in zip(tickers, best_combo):
        new_portfolio[ticker] = {
            **DEFAULT_PORTFOLIO[ticker],
            "ma_fast": fast,
            "ma_slow": slow,
        }
    return new_portfolio


def _print_comparison(current_m: dict, recommended_m: dict,
                      current_portfolio: dict, recommended_portfolio: dict,
                      tickers: list):
    print(f"\n{'='*60}")
    print(f"  Comparison: current vs recommended")
    print(f"{'='*60}")
    print(f"  {'':30s} {'Current':>10} {'Recommended':>12}")
    print(f"  {'-'*30} {'-'*10} {'-'*12}")

    for label, key, fmt in [
        ("CAGR",         "cagr",   "{:>10.1%} {:>12.1%}"),
        ("Sharpe",       "sharpe", "{:>10.2f} {:>12.2f}"),
        ("Max drawdown", "max_dd", "{:>10.1%} {:>12.1%}"),
    ]:
        print(f"  {label:30s} " + fmt.format(current_m[key], recommended_m[key]))

    print(f"\n  Config changes:")
    for ticker in tickers:
        cur = current_portfolio[ticker]
        rec = recommended_portfolio[ticker]
        cur_label = f"MA{cur['ma_fast']}/{cur['ma_slow']}"
        rec_label = f"MA{rec['ma_fast']}/{rec['ma_slow']}"
        changed = cur_label != rec_label
        marker  = "  →" if changed else "  ="
        print(f"  {marker} {ticker}: {cur_label}  →  {rec_label}"
              if changed else f"  {marker} {ticker}: {cur_label}  (unchanged)")

    sharpe_delta = recommended_m["sharpe"] - current_m["sharpe"]
    cagr_delta   = recommended_m["cagr"]   - current_m["cagr"]
    print(f"\n  CAGR delta   : {cagr_delta:+.1%}")
    print(f"  Sharpe delta : {sharpe_delta:+.2f}")

    improved = recommended_m["sharpe"] > current_m["sharpe"]
    print(f"\n  Verdict: {'IMPROVED — apply with --apply' if improved else 'NO IMPROVEMENT — keep current'}")
    return improved


def _apply_changes(recommended_portfolio: dict, tickers: list):
    """Write new params into core/portfolio_config.py in-place."""
    import pathlib

    config_path = pathlib.Path(__file__).parent.parent / "core" / "portfolio_config.py"

    text = config_path.read_text()
    for ticker in tickers:
        cfg  = recommended_portfolio[ticker]
        fast, slow = cfg["ma_fast"], cfg["ma_slow"]
        # Match pattern: "TICKER": dict(...ma_fast=XX, ma_slow=YY...)
        pattern = (
            r'("' + ticker + r'":\s*dict\([^)]*ma_fast=)\d+([^)]*ma_slow=)\d+')
        replacement = r'\g<1>' + str(fast) + r'\g<2>' + str(slow)
        new_text = re.sub(pattern, replacement, text)
        if new_text == text:
            print(f"  WARNING: could not update {ticker} in core/portfolio_config.py — update manually.")
        else:
            text = new_text
    config_path.write_text(text)

    print(f"\n  Applied changes to core/portfolio_config.py.")
    print(f"  Run `python -m tools.portfolio` to verify the full backtest.")


# ── main ─────────────────────────────────────────────────────────────────────

def tune(portfolio: dict, apply: bool = False):
    print("Step 1/3 — Portfolio-level walk-forward optimization")
    print("="*60)
    result = optimize(portfolio)
    if result is None:
        print("Optimization produced no results. Aborting.")
        return

    ranked, tickers = result

    print("\nStep 2/3 — Backtesting current vs recommended params")
    print("="*60)

    recommended_portfolio = _build_recommended(tickers, ranked)
    current_portfolio     = {t: portfolio[t] for t in tickers}

    cur_label = ", ".join(f"{t}:MA{portfolio[t]['ma_fast']}/{portfolio[t]['ma_slow']}" for t in tickers)
    print(f"  Running current   ({cur_label})...")
    current_m     = _run_portfolio(current_portfolio)

    best_combo    = ranked[0][0]
    best_label    = _combo_label(tickers, best_combo)
    print(f"  Running recommended ({best_label})...")
    recommended_m = _run_portfolio(recommended_portfolio)

    print("\nStep 3/3 — Recommendation")
    print("="*60)
    improved = _print_comparison(
        current_m, recommended_m,
        current_portfolio, recommended_portfolio,
        tickers
    )

    if apply:
        if improved:
            print(f"\n  Applying changes (--apply)...")
            _apply_changes(recommended_portfolio, tickers)
        else:
            print(f"\n  --apply skipped: recommended params don't improve Sharpe.")


if __name__ == "__main__":
    args  = sys.argv[1:]
    apply = "--apply" in args
    tune(DEFAULT_PORTFOLIO, apply=apply)
