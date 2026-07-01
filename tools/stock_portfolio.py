"""
N-stock portfolio backtester with equal or specified weighting.

Each ticker runs its own signal independently.
Weights are equal by default or specified as TICKER:weight.

Usage:
  python -m tools.stock_portfolio NVDA MSFT AAPL
  python -m tools.stock_portfolio NVDA:0.4 MSFT:0.3 AAPL:0.3
  python -m tools.stock_portfolio NVDA MSFT AAPL --strategy momentum
  python -m tools.stock_portfolio NVDA MSFT AAPL --strategy mean_rev
"""

import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core import config
from core.data import fetch
from core.metrics import calc
from core.simulator import run as simulate
from signals import ma as sig_ma
from signals import ma_3tier as sig_ma3t
from signals import rsi_band as sig_rsi_band
from strategies import momentum as strat_momentum
from strategies import momentum_3t as strat_3t
from strategies import mean_reversion as strat_mr

MOM_FAST  = 50
MOM_SLOW  = 100
MOM_SLOW3 = 200
MR_PERIOD = 14
MR_OS     = 30
MR_OB     = 70


def _run_leg(ticker: str, strategy: str, **kwargs) -> dict | None:
    try:
        prices = fetch(ticker)
    except Exception:
        print(f"{ticker}: failed to fetch.")
        return None
    min_len = kwargs.get("slow", MOM_SLOW3) if strategy == "momentum_3t" else MOM_SLOW
    if len(prices) < min_len + 10:
        print(f"{ticker}: not enough data.")
        return None

    if strategy == "momentum":
        sig = sig_ma.signal(prices, MOM_FAST, MOM_SLOW)
        pos = strat_momentum.positions(sig)
    elif strategy == "mean_rev":
        sig = sig_rsi_band.signal(prices, MR_PERIOD, MR_OS, MR_OB)
        pos = strat_mr.positions(sig)
    else:  # momentum_3t — caller passes fast/mid/slow via kwargs
        fast = kwargs.get("fast", 20)
        mid  = kwargs.get("mid",  75)
        slow = kwargs.get("slow", MOM_SLOW3)
        sig  = sig_ma3t.signal(prices, fast, mid, slow)
        pos  = strat_3t.positions(sig)

    result  = simulate(prices, pos)
    eq      = result["equity"]
    bah_prices = prices.reindex(eq.index)
    bah     = config.INITIAL_CAPITAL * (bah_prices / bah_prices.iloc[0])

    return {
        "ticker":  ticker,
        "strategy": strategy,
        "equity":  eq,
        "bah":     bah,
        "strat_m": calc(eq),
        "bah_m":   calc(bah),
        "fees":    result["total_fees"],
        "mcalls":  result["margin_calls"],
    }


def _combine(legs: list, weights: list) -> tuple[pd.Series, pd.Series]:
    """Combine weighted normalized equity curves into a single portfolio series."""
    common = legs[0]["equity"].index
    for leg in legs[1:]:
        common = common.intersection(leg["equity"].index)

    portfolio = pd.Series(0.0, index=common)
    bah_port  = pd.Series(0.0, index=common)

    for leg, w in zip(legs, weights):
        eq  = leg["equity"].reindex(common)
        bah = leg["bah"].reindex(common)
        portfolio += w * (eq  / eq.iloc[0])
        bah_port  += w * (bah / bah.iloc[0])

    return portfolio * config.INITIAL_CAPITAL, bah_port * config.INITIAL_CAPITAL


def _print_per_leg(legs, weights):
    print(f"\n{'='*72}")
    print(f"  Per-leg performance")
    print(f"{'='*72}")
    print(f"  {'Ticker':<8} {'Weight':>7} {'B&H CAGR':>9} {'Strat CAGR':>11} "
          f"{'Alpha':>7} {'Sharpe':>7} {'MaxDD':>8}")
    print(f"  {'-'*8} {'-'*7} {'-'*9} {'-'*11} {'-'*7} {'-'*7} {'-'*8}")
    for leg, w in zip(legs, weights):
        b, s = leg["bah_m"], leg["strat_m"]
        alpha = s["cagr"] - b["cagr"]
        print(f"  {leg['ticker']:<8} {w:>7.1%} {b['cagr']:>9.1%} {s['cagr']:>11.1%} "
              f"{alpha:>+7.1%} {s['sharpe']:>7.2f} {s['max_dd']:>8.1%}")


def _print_portfolio(port_m, bah_m, legs):
    total_fees  = sum(leg["fees"]   for leg in legs)
    total_mcall = sum(leg["mcalls"] for leg in legs)

    print(f"\n{'='*50}")
    print(f"  Portfolio aggregate")
    print(f"{'='*50}")
    print(f"  {'':30s} {'B&H':>10} {'Strategy':>10}")
    for label, key, fmt in [
        ("Total return", "total",  ".1%"),
        ("CAGR",         "cagr",   ".1%"),
        ("Sharpe ratio", "sharpe", ".2f"),
        ("Max drawdown", "max_dd", ".1%"),
    ]:
        print(f"  {label:30s} {bah_m[key]:>10{fmt}} {port_m[key]:>10{fmt}}")
    print(f"  {'Margin calls':30s} {'':>10} {total_mcall:>10}")
    print(f"  {'Total fees':30s} {'':>10} ${total_fees:>9,.2f}")


def _print_yearly(port_equity, bah_equity):
    years = sorted(set(port_equity.index.year))
    print(f"\n  {'Year':<6} {'B&H':>8} {'Strategy':>10} {'vs B&H':>8} {'MaxDD':>8}")
    print(f"  {'-'*6} {'-'*8} {'-'*10} {'-'*8} {'-'*8}")
    for yr in years:
        mask = port_equity.index.year == yr
        b = bah_equity[mask]
        s = port_equity[mask]
        if len(b) < 2 or len(s) < 2:
            continue
        bah_ret  = b.iloc[-1] / b.iloc[0] - 1
        strat_ret = s.iloc[-1] / s.iloc[0] - 1
        dd = ((s - s.cummax()) / s.cummax()).min()
        print(f"  {yr:<6} {bah_ret:>8.1%} {strat_ret:>10.1%} "
              f"{strat_ret - bah_ret:>+8.1%} {dd:>8.1%}")


def plot(legs, weights, port_equity, bah_equity, strategy):
    n = len(legs)
    colors = plt.cm.tab10.colors

    fig, axes = plt.subplots(3, 1, figsize=(13, 14),
                             gridspec_kw={"height_ratios": [2, 1.5, 1]})

    # Portfolio equity
    ax = axes[0]
    ax.plot(bah_equity.index, bah_equity.values,
            label="B&H (equal weight)", color="steelblue", linewidth=1.5)
    ax.plot(port_equity.index, port_equity.values,
            label=f"Strategy ({strategy})", color="darkorange", linewidth=1.5)
    pm, bm = calc(port_equity), calc(bah_equity)
    ax.set_title(
        f"Portfolio — B&H CAGR {bm['cagr']:.1%}, Sharpe {bm['sharpe']:.2f}  |  "
        f"Strategy CAGR {pm['cagr']:.1%}, Sharpe {pm['sharpe']:.2f}, MaxDD {pm['max_dd']:.1%}",
        fontsize=9)
    ax.set_ylabel("Portfolio Value ($)")
    ax.legend(fontsize=9); ax.grid(alpha=0.3)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # Per-leg equity
    ax = axes[1]
    common = legs[0]["equity"].index
    for leg in legs[1:]:
        common = common.intersection(leg["equity"].index)
    for i, (leg, w) in enumerate(zip(legs, weights)):
        eq = leg["equity"].reindex(common)
        ax.plot(eq.index, eq.values,
                label=f"{leg['ticker']} ({w:.0%})", color=colors[i % 10], linewidth=1.2)
    ax.set_title("Per-leg strategy equity", fontsize=9)
    ax.set_ylabel("Value ($)")
    ax.legend(fontsize=7, ncol=min(n, 5)); ax.grid(alpha=0.3)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # Year-by-year bars
    ax = axes[2]
    years   = sorted(set(port_equity.index.year))
    bah_rets, strat_rets = [], []
    for yr in years:
        mask = port_equity.index.year == yr
        b = bah_equity[mask]; s = port_equity[mask]
        if len(b) < 2 or len(s) < 2:
            continue
        bah_rets.append(b.iloc[-1] / b.iloc[0] - 1)
        strat_rets.append(s.iloc[-1] / s.iloc[0] - 1)
    x = np.arange(len(years))
    bar_w = 0.35
    ax.bar(x - bar_w/2, bah_rets,   bar_w, label="B&H",     color="steelblue",   alpha=0.8)
    ax.bar(x + bar_w/2, strat_rets, bar_w, label="Strategy", color="darkorange",  alpha=0.8)
    ax.set_xticks(x); ax.set_xticklabels(years, fontsize=8)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_title("Year-by-year: B&H vs Strategy", fontsize=9)
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)

    tickers_str = " + ".join(f"{leg['ticker']}({w:.0%})" for leg, w in zip(legs, weights))
    fig.suptitle(f"Stock Portfolio — {tickers_str}", fontsize=10, y=1.01)
    plt.tight_layout()

    from datetime import date as _date
    path = f"charts/portfolio/stock_portfolio_{_date.today()}.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to {path}")
    plt.close()


def portfolio(specs: list[tuple[str, float]], strategy: str, **kwargs) -> None:
    print(f"Fetching {len(specs)} tickers...")
    legs, valid_weights = [], []
    for ticker, weight in specs:
        leg = _run_leg(ticker, strategy, **kwargs)
        if leg:
            legs.append(leg)
            valid_weights.append(weight)

    if not legs:
        print("No valid tickers.")
        return

    # Renormalize weights in case some tickers failed
    total_w = sum(valid_weights)
    valid_weights = [w / total_w for w in valid_weights]

    port_equity, bah_equity = _combine(legs, valid_weights)

    _print_per_leg(legs, valid_weights)
    _print_portfolio(calc(port_equity), calc(bah_equity), legs)
    _print_yearly(port_equity, bah_equity)
    plot(legs, valid_weights, port_equity, bah_equity, strategy)


if __name__ == "__main__":
    args     = sys.argv[1:]
    strategy = "momentum"
    kwargs   = {}

    if "--strategy" in args:
        idx = args.index("--strategy")
        strategy = args[idx + 1]
        args = [a for j, a in enumerate(args) if j != idx and j != idx + 1]

    if "--ma" in args:
        idx   = args.index("--ma")
        parts = args[idx + 1].split(":")
        kwargs["fast"] = int(parts[0])
        kwargs["mid"]  = int(parts[1])
        kwargs["slow"] = int(parts[2]) if len(parts) > 2 else 200
        args = [a for j, a in enumerate(args) if j != idx and j != idx + 1]

    if not args:
        print("Usage: python -m tools.stock_portfolio TICKER[:weight] ... "
              "[--strategy momentum|momentum_3t|mean_rev] [--ma fast:mid]")
        sys.exit(1)

    specs = []
    for arg in args:
        parts  = arg.upper().split(":")
        ticker = parts[0]
        weight = float(parts[1]) if len(parts) > 1 else None
        specs.append((ticker, weight))

    n     = len(specs)
    specs = [(t, w if w is not None else 1.0 / n) for t, w in specs]
    total = sum(w for _, w in specs)
    specs = [(t, w / total) for t, w in specs]

    print(f"Portfolio: {', '.join(f'{t}({w:.1%})' for t, w in specs)}")
    print(f"Strategy: {strategy}" + (f"  |  MA: {kwargs}" if kwargs else ""))
    portfolio(specs, strategy, **kwargs)
