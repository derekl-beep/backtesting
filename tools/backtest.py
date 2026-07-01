"""
Run a backtest for one or more tickers.

Strategy: MA50/100 crossover.
Validated via walk-forward (2022-2024) + final holdout (2025-present).

Usage:
  python -m tools.backtest                  # default tickers
  python -m tools.backtest SPMO QQQ SPY
"""

import sys
import matplotlib.pyplot as plt

from core import config
from core.data import fetch
from core.metrics import calc, print_comparison
from core.simulator import run as simulate
from signals import ma as sig_ma
from strategies import momentum

MA_FAST = 50
MA_SLOW = 100


def _signal(prices):
    return sig_ma.signal(prices, MA_FAST, MA_SLOW)


def backtest(ticker: str):
    prices = fetch(ticker)
    if len(prices) < MA_SLOW + 10:
        print(f"{ticker}: not enough data.")
        return None

    sig    = _signal(prices)
    pos    = momentum.positions(sig)
    result = simulate(prices, pos)

    bah_prices = prices.reindex(result["equity"].index)
    bah_equity = config.INITIAL_CAPITAL * (bah_prices / bah_prices.iloc[0])

    bah_m   = calc(bah_equity)
    strat_m = calc(result["equity"])

    print_comparison(ticker, bah_m, strat_m, result["margin_calls"], result["total_fees"])

    return {
        "ticker":        ticker,
        "bah_equity":    bah_equity,
        "bah_m":         bah_m,
        "strat_equity":  result["equity"],
        "strat_leverage": result["leverage"],
        "strat_m":       strat_m,
        "margin_calls":  result["margin_calls"],
        "total_fees":    result["total_fees"],
    }


def plot(results: list, ma_fast: int, ma_slow: int):
    n = len(results)
    fig, axes = plt.subplots(n * 2, 1, figsize=(13, 5 * n),
                             gridspec_kw={"height_ratios": [3, 1] * n}, squeeze=False)
    colors = ["darkorange", "green", "crimson", "purple", "brown"]

    for i, r in enumerate(results):
        ax_eq  = axes[i * 2][0]
        ax_lev = axes[i * 2 + 1][0]
        ticker = r["ticker"]
        color  = colors[i % len(colors)]

        ax_eq.plot(r["bah_equity"].index, r["bah_equity"].values,
                   label=f"{ticker} Buy & Hold", color="steelblue", linewidth=1.5)
        ax_eq.plot(r["strat_equity"].index, r["strat_equity"].values,
                   label=f"{ticker} Strategy ({config.LEVERAGE}x)", color=color, linewidth=1.5)

        # Shade leveraged periods
        lev = r["strat_leverage"]
        leveraged = lev >= config.LEVERAGE
        in_block, block_start = False, None
        for date, is_lev in leveraged.items():
            if is_lev and not in_block:
                block_start, in_block = date, True
            elif not is_lev and in_block:
                ax_eq.axvspan(block_start, date, alpha=0.08, color=color, linewidth=0)
                in_block = False
        if in_block:
            ax_eq.axvspan(block_start, leveraged.index[-1], alpha=0.08, color=color, linewidth=0)

        bah_m, strat_m = r["bah_m"], r["strat_m"]
        ax_eq.set_title(
            f"{ticker} — B&H: CAGR {bah_m['cagr']:.1%}, Sharpe {bah_m['sharpe']:.2f}, "
            f"MaxDD {bah_m['max_dd']:.1%}   |   Strategy: CAGR {strat_m['cagr']:.1%}, "
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

    fig.suptitle(
        f"Strategy: MA{ma_fast}/{ma_slow}, {config.LEVERAGE}x, "
        f"{config.MARGIN_RATE:.1%} borrow", fontsize=11, y=1.01)

    plt.tight_layout()
    plt.savefig("backtest_results.png", dpi=150, bbox_inches="tight")
    print("\nChart saved to backtest_results.png")
    plt.show()


if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else config.DEFAULT_TICKERS
    ma_fast, ma_slow = 50, 100

    print(f"Fetching data for: {', '.join(tickers)}...")
    results = [r for t in tickers if (r := backtest(t)) is not None]
    if results:
        plot(results, MA_FAST, MA_SLOW)
