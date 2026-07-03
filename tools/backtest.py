"""
Run a backtest for one or more tickers.

Uses each ticker's MA params from PORTFOLIO in core/portfolio_config.py
(e.g. SPMO → MA10/200, GLD → MA20/100). Falls back to MA50/100 for
tickers not in the portfolio. Chart labels show which params were used.

Usage:
  python -m tools.backtest                  # all portfolio tickers
  python -m tools.backtest SPMO QQQ SPY
"""

import sys
from datetime import date as _date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from core import config
from core.data import fetch
from core.metrics import calc, print_comparison
from core.portfolio_config import PORTFOLIO, DEFAULT_SIGNAL
from core.simulator import run as simulate
from signals import ma as sig_ma
from strategies import momentum

CHART_DIR   = Path(__file__).parent.parent / "charts" / "backtest"
DEFAULT_MA_FAST = 50
DEFAULT_MA_SLOW = 100


def _params(ticker: str) -> tuple[int, int]:
    """Return (ma_fast, ma_slow) for ticker — portfolio config if known, else defaults."""
    cfg = PORTFOLIO.get(ticker, DEFAULT_SIGNAL)
    return cfg["ma_fast"], cfg["ma_slow"]


def backtest(ticker: str):
    ma_fast, ma_slow = _params(ticker)
    prices = fetch(ticker)
    if len(prices) < ma_slow + 10:
        print(f"{ticker}: not enough data.")
        return None

    sig    = sig_ma.signal(prices, ma_fast, ma_slow)
    pos    = momentum.positions(sig)
    result = simulate(prices, pos)

    bah_prices = prices.reindex(result["equity"].index)
    bah_equity = config.INITIAL_CAPITAL * (bah_prices / bah_prices.iloc[0])

    bah_m   = calc(bah_equity)
    strat_m = calc(result["equity"])

    print_comparison(ticker, bah_m, strat_m, result["margin_calls"], result["total_fees"])
    _print_yearly(bah_equity, result["equity"], result["leverage"])

    return {
        "ticker":         ticker,
        "ma_fast":        ma_fast,
        "ma_slow":        ma_slow,
        "bah_equity":     bah_equity,
        "bah_m":          bah_m,
        "strat_equity":   result["equity"],
        "strat_leverage": result["leverage"],
        "strat_m":        strat_m,
        "margin_calls":   result["margin_calls"],
        "total_fees":     result["total_fees"],
    }


def _print_yearly(bah: pd.Series, strat: pd.Series, leverage: pd.Series):
    years = sorted(set(bah.index.year))
    print(f"\n  {'Year':<6} {'B&H':>8} {'Strategy':>10} {'vs B&H':>8} "
          f"{'MaxDD':>8} {'Margin days':>12}")
    print(f"  {'-'*6} {'-'*8} {'-'*10} {'-'*8} {'-'*8} {'-'*12}")
    for yr in years:
        b = bah[bah.index.year == yr]
        s = strat[strat.index.year == yr]
        lev = leverage[leverage.index.year == yr]
        if len(b) < 2 or len(s) < 2:
            continue
        bah_ret  = b.iloc[-1] / b.iloc[0] - 1
        strat_ret = s.iloc[-1] / s.iloc[0] - 1
        max_dd   = ((s / s.cummax()) - 1).min()
        margin_days = int((lev >= config.LEVERAGE).sum())
        print(f"  {yr:<6} {bah_ret:>8.1%} {strat_ret:>10.1%} {strat_ret-bah_ret:>+8.1%} "
              f"{max_dd:>8.1%} {margin_days:>12}")


def plot(results: list):
    n = len(results)
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(n * 2, 1, figsize=(13, 5 * n),
                             gridspec_kw={"height_ratios": [3, 1] * n}, squeeze=False)
    colors = ["darkorange", "green", "crimson", "purple", "brown"]

    for i, r in enumerate(results):
        ax_eq  = axes[i * 2][0]
        ax_lev = axes[i * 2 + 1][0]
        ticker = r["ticker"]
        color  = colors[i % len(colors)]
        ma_fast, ma_slow = r["ma_fast"], r["ma_slow"]

        ax_eq.plot(r["bah_equity"].index, r["bah_equity"].values,
                   label=f"{ticker} Buy & Hold", color="steelblue", linewidth=1.5)
        ax_eq.plot(r["strat_equity"].index, r["strat_equity"].values,
                   label=f"{ticker} MA{ma_fast}/{ma_slow} ({config.LEVERAGE}x)",
                   color=color, linewidth=1.5)

        lev = r["strat_leverage"]
        leveraged = lev >= config.LEVERAGE
        in_block, block_start = False, None
        for dt, is_lev in leveraged.items():
            if is_lev and not in_block:
                block_start, in_block = dt, True
            elif not is_lev and in_block:
                ax_eq.axvspan(block_start, dt, alpha=0.08, color=color, linewidth=0)
                in_block = False
        if in_block:
            ax_eq.axvspan(block_start, leveraged.index[-1], alpha=0.08, color=color, linewidth=0)

        bah_m, strat_m = r["bah_m"], r["strat_m"]
        ax_eq.set_title(
            f"{ticker} MA{ma_fast}/{ma_slow} — "
            f"B&H: CAGR {bah_m['cagr']:.1%}, Sharpe {bah_m['sharpe']:.2f}, MaxDD {bah_m['max_dd']:.1%}"
            f"   |   Strategy: CAGR {strat_m['cagr']:.1%}, "
            f"Sharpe {strat_m['sharpe']:.2f}, MaxDD {strat_m['max_dd']:.1%}", fontsize=9)
        ax_eq.set_ylabel("Portfolio Value ($)")
        ax_eq.legend(fontsize=9)
        ax_eq.grid(alpha=0.3)
        ax_eq.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

        ax_lev.fill_between(lev.index, lev.values, 1, step="post",
                            alpha=0.5, color=color, label=f"Margin ON ({config.LEVERAGE}x)")
        ax_lev.axhline(1.0, color="gray", linewidth=0.8, linestyle="--")
        ax_lev.set_ylabel("Leverage")
        ax_lev.set_ylim(0.5, config.LEVERAGE + 0.3)
        ax_lev.set_yticks([1.0, config.LEVERAGE])
        ax_lev.set_yticklabels(["1x\n(no margin)", f"{config.LEVERAGE}x\n(margin)"], fontsize=7)
        ax_lev.legend(fontsize=8, loc="upper left")
        ax_lev.grid(alpha=0.3)

    plt.tight_layout()
    out = CHART_DIR / f"backtest_results_{_date.today()}.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to {out}")
    plt.close(fig)


if __name__ == "__main__":
    tickers = [t.upper() for t in sys.argv[1:]] if len(sys.argv) > 1 else list(PORTFOLIO)
    print(f"Fetching data for: {', '.join(tickers)}...")
    results = [r for t in tickers if (r := backtest(t)) is not None]
    if results:
        plot(results)
