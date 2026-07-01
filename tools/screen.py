"""
ETF screener for portfolio construction.

Fetches candidate tickers, shows correlation matrix and per-ticker
strategy stats so you can pick low-correlated, high-performing ETFs.

Usage:
  python -m tools.screen SPMO VGT VOO TLT GLD EEM IWM
"""

import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

from core import config
from core.data import fetch
from core.metrics import calc
from core.simulator import run as simulate
from signals import ma as sig_ma
from strategies import momentum

MA_FAST = 50
MA_SLOW = 100

DEFAULT_TICKERS = ["SPMO", "VGT", "VOO", "TLT", "GLD", "EEM", "IWM"]


def _run_ticker(ticker: str) -> dict | None:
    try:
        prices = fetch(ticker)
    except Exception:
        print(f"{ticker}: failed to fetch.")
        return None
    if len(prices) < MA_SLOW + 10:
        print(f"{ticker}: not enough data.")
        return None

    sig = sig_ma.signal(prices, MA_FAST, MA_SLOW)
    pos = momentum.positions(sig)
    result = simulate(prices, pos)

    bah_prices = prices.reindex(result["equity"].index)
    bah_equity = config.INITIAL_CAPITAL * (bah_prices / bah_prices.iloc[0])

    return {
        "ticker":  ticker,
        "prices":  prices,
        "equity":  result["equity"],
        "bah":     bah_equity,
        "bah_m":   calc(bah_equity),
        "strat_m": calc(result["equity"]),
    }


def screen(tickers: list[str]) -> None:
    print(f"Fetching {len(tickers)} tickers...")
    legs = [r for t in tickers if (r := _run_ticker(t)) is not None]
    if len(legs) < 2:
        print("Need at least 2 tickers.")
        return

    # Align to common date range
    common_idx = legs[0]["prices"].index
    for leg in legs[1:]:
        common_idx = common_idx.intersection(leg["prices"].index)

    # Daily returns for correlation
    returns = pd.DataFrame({
        leg["ticker"]: leg["prices"].reindex(common_idx).pct_change().dropna()
        for leg in legs
    })
    corr = returns.corr()

    _print_stats(legs, common_idx)
    _print_correlation(corr)
    plot(legs, corr, common_idx)


def _print_stats(legs, common_idx):
    print(f"\n{'='*72}")
    print(f" Per-ticker performance  (MA{MA_FAST}/{MA_SLOW}, common period "
          f"{common_idx[0].date()} – {common_idx[-1].date()})")
    print(f"{'='*72}")
    print(f"  {'Ticker':<8} {'B&H CAGR':>9} {'Strat CAGR':>11} {'Alpha':>7} "
          f"{'Sharpe':>7} {'MaxDD':>8}")
    print(f"  {'-'*8} {'-'*9} {'-'*11} {'-'*7} {'-'*7} {'-'*8}")
    for leg in legs:
        b = leg["bah_m"]
        s = leg["strat_m"]
        alpha = s["cagr"] - b["cagr"]
        print(f"  {leg['ticker']:<8} {b['cagr']:>9.1%} {s['cagr']:>11.1%} "
              f"{alpha:>+7.1%} {s['sharpe']:>7.2f} {s['max_dd']:>8.1%}")


def _print_correlation(corr: pd.DataFrame):
    tickers = corr.columns.tolist()
    print(f"\n  Correlation matrix (daily returns):")
    w = 8
    header = f"  {'':8}" + "".join(f"{t:>{w}}" for t in tickers)
    print(header)
    for t in tickers:
        row = f"  {t:<8}" + "".join(
            f"{corr.loc[t, t2]:>{w}.2f}" for t2 in tickers
        )
        print(row)


def plot(legs, corr: pd.DataFrame, common_idx):
    tickers = [leg["ticker"] for leg in legs]
    n = len(tickers)

    fig = plt.figure(figsize=(14, 10))
    gs  = fig.add_gridspec(2, 2, width_ratios=[1.2, 1], height_ratios=[1, 1],
                           hspace=0.4, wspace=0.35)

    ax_eq   = fig.add_subplot(gs[0, :])   # equity curves — full width
    ax_corr = fig.add_subplot(gs[1, 0])   # correlation heatmap
    ax_bar  = fig.add_subplot(gs[1, 1])   # strategy CAGR bar chart

    colors = plt.cm.tab10.colors

    # Equity curves
    for i, leg in enumerate(legs):
        eq = leg["equity"].reindex(common_idx)
        ax_eq.plot(eq.index, eq.values, label=leg["ticker"],
                   color=colors[i % len(colors)], linewidth=1.4)
    ax_eq.set_title(f"Strategy equity curves  (MA{MA_FAST}/{MA_SLOW}, 2x leverage when bullish)",
                    fontsize=9)
    ax_eq.set_ylabel("Portfolio Value ($)")
    ax_eq.legend(fontsize=8, ncol=min(n, 4))
    ax_eq.grid(alpha=0.3)
    ax_eq.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # Correlation heatmap
    corr_vals = corr.values
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "rg", ["#2ecc71", "#f9f9f9", "#e74c3c"]
    )
    im = ax_corr.imshow(corr_vals, cmap=cmap, vmin=-1, vmax=1, aspect="auto")
    ax_corr.set_xticks(range(n))
    ax_corr.set_yticks(range(n))
    ax_corr.set_xticklabels(tickers, fontsize=8, rotation=45, ha="right")
    ax_corr.set_yticklabels(tickers, fontsize=8)
    for i in range(n):
        for j in range(n):
            val = corr_vals[i, j]
            ax_corr.text(j, i, f"{val:.2f}", ha="center", va="center",
                         fontsize=7, color="black" if abs(val) < 0.7 else "white")
    fig.colorbar(im, ax=ax_corr, shrink=0.8)
    ax_corr.set_title("Return correlation", fontsize=9)

    # CAGR bar chart: B&H vs strategy
    x      = np.arange(n)
    bah_cagrs   = [leg["bah_m"]["cagr"] for leg in legs]
    strat_cagrs = [leg["strat_m"]["cagr"] for leg in legs]
    bar_w  = 0.35
    ax_bar.bar(x - bar_w / 2, bah_cagrs,   bar_w, label="B&H",     color="steelblue", alpha=0.8)
    ax_bar.bar(x + bar_w / 2, strat_cagrs, bar_w, label="Strategy", color="darkorange", alpha=0.8)
    ax_bar.set_xticks(x)
    ax_bar.set_xticklabels(tickers, fontsize=8)
    ax_bar.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
    ax_bar.axhline(0, color="gray", linewidth=0.8)
    ax_bar.set_title("CAGR: B&H vs Strategy", fontsize=9)
    ax_bar.legend(fontsize=8)
    ax_bar.grid(axis="y", alpha=0.3)

    fig.suptitle(
        f"ETF Screener — {', '.join(tickers)} | "
        f"{common_idx[0].date()} – {common_idx[-1].date()}",
        fontsize=11)

    plt.savefig("screen_results.png", dpi=150, bbox_inches="tight")
    print("\nChart saved to screen_results.png")
    plt.show()


if __name__ == "__main__":
    tickers = [t.upper() for t in sys.argv[1:]] if sys.argv[1:] else DEFAULT_TICKERS
    screen(tickers)
