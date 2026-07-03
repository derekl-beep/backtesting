"""
ETF screener for portfolio construction.

Evaluates each candidate with its own MA params: uses PORTFOLIO config for
known tickers, DEFAULT_SIGNAL (MA50/100) for new candidates. This ensures
SPMO and GLD are assessed at their actual configured params, while new ETFs
are screened at a neutral baseline before you run optimize on them.

Usage:
  python -m tools.screen SPMO VGT VOO TLT GLD EEM IWM
"""

import sys
from datetime import date as _date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd

from core import config
from core.data import fetch
from core.metrics import calc
from core.portfolio_config import PORTFOLIO, DEFAULT_SIGNAL
from core.simulator import run as simulate
from signals import ma as sig_ma
from strategies import momentum

CHART_DIR = Path(__file__).parent.parent / "charts" / "screen"
DEFAULT_TICKERS = ["SPMO", "VGT", "VOO", "TLT", "GLD", "EEM", "IWM", "EWJ", "NUKZ"]


def _ticker_params(ticker: str) -> tuple[int, int]:
    cfg = PORTFOLIO.get(ticker, DEFAULT_SIGNAL)
    return cfg["ma_fast"], cfg["ma_slow"]


def _run_ticker(ticker: str) -> dict | None:
    ma_fast, ma_slow = _ticker_params(ticker)
    try:
        prices = fetch(ticker)
    except Exception:
        print(f"{ticker}: failed to fetch.")
        return None
    if len(prices) < ma_slow + 10:
        print(f"{ticker}: not enough data.")
        return None

    sig = sig_ma.signal(prices, ma_fast, ma_slow)
    pos = momentum.positions(sig)
    result = simulate(prices, pos)

    bah_prices = prices.reindex(result["equity"].index)
    bah_equity = config.INITIAL_CAPITAL * (bah_prices / bah_prices.iloc[0])

    return {
        "ticker":  ticker,
        "ma_fast": ma_fast,
        "ma_slow": ma_slow,
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

    common_idx = legs[0]["prices"].index
    for leg in legs[1:]:
        common_idx = common_idx.intersection(leg["prices"].index)

    returns = pd.DataFrame({
        leg["ticker"]: leg["prices"].reindex(common_idx).pct_change().dropna()
        for leg in legs
    })
    corr = returns.corr()

    _print_stats(legs, common_idx)
    _print_correlation(corr)
    plot(legs, corr, common_idx)


def _print_stats(legs, common_idx):
    print(f"\n{'='*80}")
    print(f"  Per-ticker performance  (each at its own MA params, "
          f"{common_idx[0].date()} – {common_idx[-1].date()})")
    print(f"{'='*80}")
    print(f"  {'Ticker':<8} {'Signal':<12} {'B&H CAGR':>9} {'Strat CAGR':>11} "
          f"{'Alpha':>7} {'Sharpe':>7} {'MaxDD':>8}")
    print(f"  {'-'*8} {'-'*12} {'-'*9} {'-'*11} {'-'*7} {'-'*7} {'-'*8}")
    for leg in legs:
        b = leg["bah_m"]
        s = leg["strat_m"]
        sig_label = f"MA{leg['ma_fast']}/{leg['ma_slow']}"
        alpha = s["cagr"] - b["cagr"]
        in_portfolio = "✓" if leg["ticker"] in PORTFOLIO else " "
        print(f"  {in_portfolio}{leg['ticker']:<7} {sig_label:<12} {b['cagr']:>9.1%} "
              f"{s['cagr']:>11.1%} {alpha:>+7.1%} {s['sharpe']:>7.2f} {s['max_dd']:>8.1%}")
    print(f"\n  ✓ = currently in portfolio  |  new candidates screened at MA50/100 (baseline)")


def _print_correlation(corr: pd.DataFrame):
    tickers = corr.columns.tolist()
    print(f"\n  Correlation matrix (daily returns):")
    w = 8
    print(f"  {'':8}" + "".join(f"{t:>{w}}" for t in tickers))
    for t in tickers:
        row = f"  {t:<8}" + "".join(f"{corr.loc[t, t2]:>{w}.2f}" for t2 in tickers)
        print(row)


def plot(legs, corr: pd.DataFrame, common_idx):
    tickers = [leg["ticker"] for leg in legs]
    n = len(tickers)

    CHART_DIR.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(14, 10))
    gs  = fig.add_gridspec(2, 2, width_ratios=[1.2, 1], height_ratios=[1, 1],
                           hspace=0.4, wspace=0.35)

    ax_eq   = fig.add_subplot(gs[0, :])
    ax_corr = fig.add_subplot(gs[1, 0])
    ax_bar  = fig.add_subplot(gs[1, 1])

    colors = plt.cm.tab10.colors

    for i, leg in enumerate(legs):
        eq = leg["equity"].reindex(common_idx)
        sig_label = f"MA{leg['ma_fast']}/{leg['ma_slow']}"
        ax_eq.plot(eq.index, eq.values,
                   label=f"{leg['ticker']} ({sig_label})",
                   color=colors[i % len(colors)], linewidth=1.4)
    ax_eq.set_title("Strategy equity curves — each ticker at its own MA params, 2x leverage",
                    fontsize=9)
    ax_eq.set_ylabel("Portfolio Value ($)")
    ax_eq.legend(fontsize=8, ncol=min(n, 4))
    ax_eq.grid(alpha=0.3)
    ax_eq.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    corr_vals = corr.values
    cmap = mcolors.LinearSegmentedColormap.from_list("rg", ["#2ecc71", "#f9f9f9", "#e74c3c"])
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

    x = np.arange(n)
    bah_cagrs   = [leg["bah_m"]["cagr"]   for leg in legs]
    strat_cagrs = [leg["strat_m"]["cagr"] for leg in legs]
    bar_w = 0.35
    ax_bar.bar(x - bar_w / 2, bah_cagrs,   bar_w, label="B&H",     color="steelblue",  alpha=0.8)
    ax_bar.bar(x + bar_w / 2, strat_cagrs, bar_w, label="Strategy", color="darkorange", alpha=0.8)
    ax_bar.set_xticks(x)
    ax_bar.set_xticklabels(tickers, fontsize=8)
    ax_bar.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
    ax_bar.axhline(0, color="gray", linewidth=0.8)
    ax_bar.set_title("CAGR: B&H vs Strategy", fontsize=9)
    ax_bar.legend(fontsize=8)
    ax_bar.grid(axis="y", alpha=0.3)

    fig.suptitle(
        f"ETF Screener — {', '.join(tickers)}  |  "
        f"{common_idx[0].date()} – {common_idx[-1].date()}",
        fontsize=11)

    out = CHART_DIR / f"screen_results_{_date.today()}.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to {out}")
    plt.close(fig)


if __name__ == "__main__":
    tickers = [t.upper() for t in sys.argv[1:]] if sys.argv[1:] else DEFAULT_TICKERS
    screen(tickers)
