"""
Multi-strategy comparison tool.

Runs the following variants on each ticker and compares side-by-side:
  1. MA only              (baseline)
  2. MA + RSI  (all)
  3. MA + MACD (all)
  4. MA + RSI + MACD (majority)
  5. MA + hedge (SH when bearish)

Usage:
  python -m tools.compare
  python -m tools.compare SPMO QQQ
"""

import sys
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd

from core import config
from core.data import fetch
from core.metrics import calc, print_comparison
from core.simulator import run as simulate
import signals.ma   as sig_ma
import signals.rsi  as sig_rsi
import signals.macd as sig_macd
from signals.combo import all_of, majority_of
from strategies import momentum
from strategies.hedged import run as hedged_run, HEDGE_TICKER

MA_FAST = 50
MA_SLOW = 100


def _run_variant(name, prices, signal, mode="momentum", hedge_prices=None):
    if mode == "hedge_sh":
        result = hedged_run(prices, hedge_prices, signal)
    elif mode == "cash":
        pos    = momentum.positions(signal, no_signal_leverage=0.0)
        result = simulate(prices, pos)
    else:
        pos    = momentum.positions(signal)
        result = simulate(prices, pos)

    bah_prices = prices.reindex(result["equity"].index)
    bah_equity = config.INITIAL_CAPITAL * (bah_prices / bah_prices.iloc[0])
    return {
        "name":           name,
        "bah_m":          calc(bah_equity),
        "bah_equity":     bah_equity,
        "strat_m":        calc(result["equity"]),
        "strat_equity":   result["equity"],
        "strat_leverage": result["leverage"],
        "margin_calls":   result["margin_calls"],
        "total_fees":     result["total_fees"],
    }


def compare(ticker: str):
    print(f"\nFetching {ticker} + {HEDGE_TICKER} data...")
    prices       = fetch(ticker)
    hedge_prices = fetch(HEDGE_TICKER)

    ma   = sig_ma.signal(prices, MA_FAST, MA_SLOW)
    rsi  = sig_rsi.signal(prices)
    macd = sig_macd.signal(prices)

    variants = [
        _run_variant("MA only",               prices, ma),
        _run_variant("MA + RSI + MACD (maj)", prices, majority_of([ma, rsi, macd])),
        _run_variant("MA + RSI (all)",        prices, all_of([ma, rsi])),
        _run_variant("MA + MACD (all)",       prices, all_of([ma, macd])),
        _run_variant("MA + cash (0x)",        prices, ma,  mode="cash"),
        _run_variant("MA + hedge (SH)",       prices, ma,  mode="hedge_sh", hedge_prices=hedge_prices),
    ]

    # Print summary table
    print(f"\n{'='*75}")
    print(f"  {ticker}  —  strategy comparison (MA {MA_FAST}/{MA_SLOW}, {config.LEVERAGE}x)")
    print(f"{'='*75}")
    print(f"  {'Strategy':<26} {'CAGR':>7} {'Sharpe':>7} {'MaxDD':>7} {'vs B&H':>7} {'Fees':>8} {'MC':>4}")
    print(f"  {'-'*26} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*8} {'-'*4}")

    bah_cagr = variants[0]["bah_m"]["cagr"]
    for v in variants:
        m    = v["strat_m"]
        diff = m["cagr"] - bah_cagr
        print(f"  {v['name']:<26} {m['cagr']:>7.1%} {m['sharpe']:>7.2f} "
              f"{m['max_dd']:>7.1%} {diff:>+7.1%} ${v['total_fees']:>7,.0f} {v['margin_calls']:>4}")

    print(f"\n  Buy & Hold: CAGR {bah_cagr:.1%}, "
          f"Sharpe {variants[0]['bah_m']['sharpe']:.2f}, "
          f"MaxDD {variants[0]['bah_m']['max_dd']:.1%}")

    # Plot
    colors = ["darkorange", "royalblue", "green", "purple", "crimson"]
    fig, axes = plt.subplots(2, 1, figsize=(13, 9),
                             gridspec_kw={"height_ratios": [3, 1]})
    ax_eq, ax_sig = axes

    # Buy & hold reference
    bah = variants[0]["bah_equity"]
    ax_eq.plot(bah.index, bah.values, color="steelblue", linewidth=1.5,
               linestyle="--", label="Buy & Hold", zorder=5)

    for v, color in zip(variants, colors):
        m = v["strat_m"]
        ax_eq.plot(v["strat_equity"].index, v["strat_equity"].values,
                   color=color, linewidth=1.3, alpha=0.85,
                   label=f"{v['name']}  CAGR {m['cagr']:.1%}  MaxDD {m['max_dd']:.1%}")

    ax_eq.set_title(f"{ticker}: Signal Combination & Hedge Strategy Comparison "
                    f"(MA {MA_FAST}/{MA_SLOW}, {config.LEVERAGE}x)", fontsize=10)
    ax_eq.set_ylabel("Portfolio Value ($)")
    ax_eq.legend(fontsize=8, loc="upper left")
    ax_eq.grid(alpha=0.3)
    ax_eq.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # Signal comparison panel — show which days each signal is ON
    signal_series = {
        "MA":   ma,
        "RSI":  rsi,
        "MACD": macd,
    }
    sig_colors = {"MA": "darkorange", "RSI": "royalblue", "MACD": "green"}
    offsets    = {"MA": 0.6, "RSI": 0.3, "MACD": 0.0}

    for name, s in signal_series.items():
        bullish = s[s == 1]
        ax_sig.scatter(bullish.index, [offsets[name]] * len(bullish),
                       marker="|", s=15, color=sig_colors[name],
                       alpha=0.6, label=f"{name} ON")

    ax_sig.set_yticks([0.0, 0.3, 0.6])
    ax_sig.set_yticklabels(["MACD", "RSI", "MA"], fontsize=8)
    ax_sig.set_ylabel("Signal active")
    ax_sig.set_xlabel("Date")
    ax_sig.grid(alpha=0.2)
    ax_sig.legend(fontsize=8, loc="upper left")

    plt.tight_layout()
    out = f"compare_{ticker.lower()}.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to {out}")
    plt.show()

    return variants


if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["SPMO"]
    for t in tickers:
        compare(t.upper())
