"""
Stock screener: runs momentum and mean-reversion strategies side-by-side,
showing which strategy has positive alpha per ticker.

Usage:
  python -m tools.stock_screen NVDA MSFT AAPL TSLA META
  python -m tools.stock_screen NVDA MSFT AAPL TSLA META AMZN GOOG NFLX
"""

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

from core import config
from core.data import fetch
from core.metrics import calc
from core.simulator import run as simulate
from signals import ma as sig_ma
from signals import rsi_band as sig_rsi_band
from strategies import momentum as strat_momentum
from strategies import mean_reversion as strat_mr

MOM_FAST  = 50
MOM_SLOW  = 100
MR_PERIOD = 14
MR_OS     = 30
MR_OB     = 70

DEFAULT_TICKERS = ["NVDA", "MSFT", "AAPL", "TSLA", "META", "AMZN", "GOOG"]


def _run_ticker(ticker: str) -> dict | None:
    try:
        prices = fetch(ticker)
    except Exception:
        print(f"{ticker}: failed to fetch.")
        return None
    if len(prices) < MOM_SLOW + 10:
        print(f"{ticker}: not enough data.")
        return None

    bah_equity = config.INITIAL_CAPITAL * (prices / prices.iloc[0])
    bah_m = calc(bah_equity)

    # Momentum
    sig = sig_ma.signal(prices, MOM_FAST, MOM_SLOW)
    pos = strat_momentum.positions(sig)
    mom_res = simulate(prices, pos)
    mom_equity = mom_res["equity"]
    mom_m = calc(mom_equity)

    # Mean-reversion
    sig_mr = sig_rsi_band.signal(prices, MR_PERIOD, MR_OS, MR_OB)
    pos_mr = strat_mr.positions(sig_mr)
    mr_res = simulate(prices, pos_mr)
    mr_equity = mr_res["equity"]
    mr_m = calc(mr_equity)

    mom_alpha = mom_m["cagr"] - bah_m["cagr"]
    mr_alpha  = mr_m["cagr"]  - bah_m["cagr"]

    if mom_alpha > 0 and mr_alpha > 0:
        recommended = "momentum" if mom_alpha >= mr_alpha else "mean_rev"
    elif mom_alpha > 0:
        recommended = "momentum"
    elif mr_alpha > 0:
        recommended = "mean_rev"
    else:
        recommended = "B&H"

    return {
        "ticker":      ticker,
        "prices":      prices,
        "bah_equity":  bah_equity,
        "bah_m":       bah_m,
        "mom_equity":  mom_equity,
        "mom_m":       mom_m,
        "mr_equity":   mr_equity,
        "mr_m":        mr_m,
        "mom_alpha":   mom_alpha,
        "mr_alpha":    mr_alpha,
        "recommended": recommended,
    }


def _print_stats(legs, common_idx):
    print(f"\n{'='*100}")
    print(f" Stock screener  "
          f"(Momentum: MA{MOM_FAST}/{MOM_SLOW} 2x  |  Mean-rev: RSI{MR_PERIOD} {MR_OS}/{MR_OB} 1x"
          f"  |  {common_idx[0].date()} – {common_idx[-1].date()})")
    print(f"{'='*100}")
    print(f"  {'Ticker':<8} {'B&H CAGR':>9} {'Mom CAGR':>9} {'Mom α':>7} "
          f"{'Mom Sharpe':>11} {'MR CAGR':>8} {'MR α':>7} {'MR Sharpe':>10} {'Best':>10}")
    print(f"  {'-'*8} {'-'*9} {'-'*9} {'-'*7} {'-'*11} {'-'*8} {'-'*7} {'-'*10} {'-'*10}")
    for leg in legs:
        b, m, r = leg["bah_m"], leg["mom_m"], leg["mr_m"]
        print(f"  {leg['ticker']:<8} {b['cagr']:>9.1%} {m['cagr']:>9.1%} "
              f"{leg['mom_alpha']:>+7.1%} {m['sharpe']:>11.2f} "
              f"{r['cagr']:>8.1%} {leg['mr_alpha']:>+7.1%} "
              f"{r['sharpe']:>10.2f} {leg['recommended']:>10}")


def _print_correlation(corr):
    tickers = corr.columns.tolist()
    w = 8
    print(f"\n  Correlation matrix (daily returns):")
    print(f"  {'':8}" + "".join(f"{t:>{w}}" for t in tickers))
    for t in tickers:
        print(f"  {t:<8}" + "".join(f"{corr.loc[t, t2]:>{w}.2f}" for t2 in tickers))


def plot(legs, corr, common_idx):
    tickers = [leg["ticker"] for leg in legs]
    n = len(tickers)
    colors = plt.cm.tab10.colors

    fig = plt.figure(figsize=(16, 14))
    gs = fig.add_gridspec(3, 2, hspace=0.45, wspace=0.35,
                          height_ratios=[1.6, 1, 1])
    ax_eq   = fig.add_subplot(gs[0, :])
    ax_corr = fig.add_subplot(gs[1, 0])
    ax_mom  = fig.add_subplot(gs[1, 1])
    ax_mr   = fig.add_subplot(gs[2, 0])
    ax_sh   = fig.add_subplot(gs[2, 1])

    # Equity curves: best strategy per ticker (solid) vs B&H (dashed)
    for i, leg in enumerate(legs):
        eq = (leg["mom_equity"] if leg["recommended"] in ("momentum", "B&H")
              else leg["mr_equity"]).reindex(common_idx)
        bah = leg["bah_equity"].reindex(common_idx)
        ax_eq.plot(eq.index, eq.values,
                   label=f"{leg['ticker']} ({leg['recommended']})",
                   color=colors[i % 10], linewidth=1.4)
        ax_eq.plot(bah.index, bah.values,
                   color=colors[i % 10], linewidth=0.7, linestyle="--", alpha=0.45)
    ax_eq.set_title("Best strategy (solid) vs B&H (dashed)", fontsize=9)
    ax_eq.set_ylabel("Portfolio Value ($)")
    ax_eq.legend(fontsize=7, ncol=min(n, 4))
    ax_eq.grid(alpha=0.3)
    ax_eq.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # Correlation heatmap
    corr_vals = corr.values
    cmap = mcolors.LinearSegmentedColormap.from_list("rg", ["#2ecc71", "#f9f9f9", "#e74c3c"])
    im = ax_corr.imshow(corr_vals, cmap=cmap, vmin=-1, vmax=1, aspect="auto")
    ax_corr.set_xticks(range(n)); ax_corr.set_yticks(range(n))
    ax_corr.set_xticklabels(tickers, fontsize=7, rotation=45, ha="right")
    ax_corr.set_yticklabels(tickers, fontsize=7)
    for i in range(n):
        for j in range(n):
            val = corr_vals[i, j]
            ax_corr.text(j, i, f"{val:.2f}", ha="center", va="center",
                         fontsize=6, color="black" if abs(val) < 0.7 else "white")
    fig.colorbar(im, ax=ax_corr, shrink=0.8)
    ax_corr.set_title("Return correlation", fontsize=9)

    x = np.arange(n)
    bar_w = 0.35

    # Momentum alpha
    mom_alphas = [leg["mom_alpha"] for leg in legs]
    ax_mom.bar(x, mom_alphas,
               color=["#27ae60" if a > 0 else "#e74c3c" for a in mom_alphas], alpha=0.8)
    ax_mom.set_xticks(x); ax_mom.set_xticklabels(tickers, fontsize=7)
    ax_mom.axhline(0, color="gray", linewidth=0.8)
    ax_mom.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
    ax_mom.set_title(f"Momentum alpha (MA{MOM_FAST}/{MOM_SLOW} 2x vs B&H)", fontsize=9)
    ax_mom.grid(axis="y", alpha=0.3)

    # Mean-rev alpha
    mr_alphas = [leg["mr_alpha"] for leg in legs]
    ax_mr.bar(x, mr_alphas,
              color=["#27ae60" if a > 0 else "#e74c3c" for a in mr_alphas], alpha=0.8)
    ax_mr.set_xticks(x); ax_mr.set_xticklabels(tickers, fontsize=7)
    ax_mr.axhline(0, color="gray", linewidth=0.8)
    ax_mr.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
    ax_mr.set_title(f"Mean-rev alpha (RSI{MR_PERIOD} {MR_OS}/{MR_OB} 1x vs B&H)", fontsize=9)
    ax_mr.grid(axis="y", alpha=0.3)

    # Sharpe comparison
    mom_sharpes = [leg["mom_m"]["sharpe"] for leg in legs]
    mr_sharpes  = [leg["mr_m"]["sharpe"]  for leg in legs]
    ax_sh.bar(x - bar_w/2, mom_sharpes, bar_w, label="Momentum", color="steelblue",   alpha=0.8)
    ax_sh.bar(x + bar_w/2, mr_sharpes,  bar_w, label="Mean-rev",  color="darkorange", alpha=0.8)
    ax_sh.set_xticks(x); ax_sh.set_xticklabels(tickers, fontsize=7)
    ax_sh.axhline(0, color="gray", linewidth=0.8)
    ax_sh.set_title("Sharpe: Momentum vs Mean-rev", fontsize=9)
    ax_sh.legend(fontsize=7)
    ax_sh.grid(axis="y", alpha=0.3)

    fig.suptitle(
        f"Stock Screener — {', '.join(tickers)} | "
        f"{common_idx[0].date()} – {common_idx[-1].date()}",
        fontsize=11)

    from datetime import date as _date
    path = f"charts/screen/stock_screen_{_date.today()}.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to {path}")
    plt.show()


def screen(tickers: list[str]) -> None:
    print(f"Fetching {len(tickers)} tickers...")
    legs = [r for t in tickers if (r := _run_ticker(t)) is not None]
    if not legs:
        print("No valid tickers.")
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
    if len(legs) > 1:
        _print_correlation(corr)
    plot(legs, corr, common_idx)


if __name__ == "__main__":
    tickers = [t.upper() for t in sys.argv[1:]] if sys.argv[1:] else DEFAULT_TICKERS
    screen(tickers)
