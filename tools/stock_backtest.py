"""
Backtest individual stocks with strategy selection.

Strategies:
  momentum  — MA50/100 crossover, 2x leverage when bullish, 1x when bearish
  mean_rev  — RSI band (14/30/70), 1x when oversold, cash when neutral/overbought
  both      — show side-by-side (default)

Usage:
  python -m tools.stock_backtest NVDA
  python -m tools.stock_backtest NVDA MSFT AAPL
  python -m tools.stock_backtest NVDA --strategy momentum
  python -m tools.stock_backtest NVDA --strategy mean_rev
"""

import sys
import pandas as pd
import matplotlib.pyplot as plt

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


def _run_momentum(prices):
    sig = sig_ma.signal(prices, MOM_FAST, MOM_SLOW)
    pos = strat_momentum.positions(sig)
    result = simulate(prices, pos)
    bah = config.INITIAL_CAPITAL * (prices.reindex(result["equity"].index) /
                                     prices.reindex(result["equity"].index).iloc[0])
    return result, bah


def _run_mean_rev(prices):
    sig = sig_rsi_band.signal(prices, MR_PERIOD, MR_OS, MR_OB)
    pos = strat_mr.positions(sig)
    result = simulate(prices, pos)
    bah = config.INITIAL_CAPITAL * (prices.reindex(result["equity"].index) /
                                     prices.reindex(result["equity"].index).iloc[0])
    return result, bah


def backtest(ticker: str, strategy: str = "both") -> dict | None:
    prices = fetch(ticker)
    if len(prices) < MOM_SLOW + 10:
        print(f"{ticker}: not enough data.")
        return None

    r = {"ticker": ticker, "strategy": strategy}

    if strategy in ("momentum", "both"):
        mom_res, bah = _run_momentum(prices)
        r["mom_res"] = mom_res
        r["mom_m"]   = calc(mom_res["equity"])
        r["bah"]     = bah
        r["bah_m"]   = calc(bah)

    if strategy in ("mean_rev", "both"):
        mr_res, bah = _run_mean_rev(prices)
        r["mr_res"] = mr_res
        r["mr_m"]   = calc(mr_res["equity"])
        if "bah_m" not in r:
            r["bah"]   = bah
            r["bah_m"] = calc(bah)

    _print_results(r)
    return r


def _print_results(r):
    strategy = r["strategy"]
    bah_m    = r["bah_m"]

    print(f"\n{'='*60}")
    print(f" {r['ticker']}")
    print(f"{'='*60}")
    header = f"  {'':30s} {'B&H':>10}"
    if strategy in ("momentum", "both"):
        header += f" {'Momentum':>10}"
    if strategy in ("mean_rev", "both"):
        header += f" {'Mean-rev':>10}"
    print(header)

    for label, key, fmt in [
        ("Total return", "total",  ".1%"),
        ("CAGR",         "cagr",   ".1%"),
        ("Sharpe ratio", "sharpe", ".2f"),
        ("Max drawdown", "max_dd", ".1%"),
    ]:
        row = f"  {label:30s} {bah_m[key]:>10{fmt}}"
        if strategy in ("momentum", "both"):
            row += f" {r['mom_m'][key]:>10{fmt}}"
        if strategy in ("mean_rev", "both"):
            row += f" {r['mr_m'][key]:>10{fmt}}"
        print(row)

    if strategy in ("momentum", "both"):
        print(f"  {'Margin calls':30s} {'':>10} {r['mom_res']['margin_calls']:>10}")
        print(f"  {'Total fees':30s} {'':>10} ${r['mom_res']['total_fees']:>9,.2f}")

    _print_yearly(r)


def _print_yearly(r):
    strategy = r["strategy"]
    bah      = r["bah"]
    mom_eq   = r["mom_res"]["equity"] if strategy in ("momentum", "both") else None
    mr_eq    = r["mr_res"]["equity"]  if strategy in ("mean_rev", "both") else None

    # Common index across all series
    idx = bah.index
    if mom_eq is not None:
        idx = idx.intersection(mom_eq.index)
    if mr_eq is not None:
        idx = idx.intersection(mr_eq.index)

    bah = bah.reindex(idx)

    header = f"\n  {'Year':<6} {'B&H':>8}"
    if mom_eq is not None:
        header += f" {'Momentum':>10} {'vs B&H':>8}"
    if mr_eq is not None:
        header += f" {'Mean-rev':>10} {'vs B&H':>8}"
    print(header)

    sep = f"  {'-'*6} {'-'*8}"
    if mom_eq is not None:
        sep += f" {'-'*10} {'-'*8}"
    if mr_eq is not None:
        sep += f" {'-'*10} {'-'*8}"
    print(sep)

    for yr in sorted(set(idx.year)):
        mask = idx.year == yr
        b = bah[mask]
        if len(b) < 2:
            continue
        bah_ret = b.iloc[-1] / b.iloc[0] - 1
        row = f"  {yr:<6} {bah_ret:>8.1%}"

        if mom_eq is not None:
            m = mom_eq.reindex(idx)[mask]
            if len(m) >= 2:
                ret = m.iloc[-1] / m.iloc[0] - 1
                row += f" {ret:>10.1%} {ret - bah_ret:>+8.1%}"
            else:
                row += f" {'N/A':>10} {'':>8}"

        if mr_eq is not None:
            mv = mr_eq.reindex(idx)[mask]
            if len(mv) >= 2:
                ret = mv.iloc[-1] / mv.iloc[0] - 1
                row += f" {ret:>10.1%} {ret - bah_ret:>+8.1%}"
            else:
                row += f" {'N/A':>10} {'':>8}"

        print(row)


def plot(results: list, strategy: str):
    if not results:
        return

    n = len(results)
    colors_mom = ["darkorange", "green", "crimson", "purple"]
    colors_mr  = ["royalblue",  "teal",  "olive",   "sienna"]

    # Rows per ticker: equity panel(s) + leverage panel (momentum only)
    rows_per = (3 if strategy == "both" else
                2 if strategy == "momentum" else
                1)
    height_ratios_unit = ([3, 3, 1] if strategy == "both" else
                          [3, 1]    if strategy == "momentum" else
                          [3])

    fig, axes = plt.subplots(
        n * rows_per, 1,
        figsize=(13, sum(height_ratios_unit) * 2 * n),
        gridspec_kw={"height_ratios": height_ratios_unit * n},
        squeeze=False,
    )

    for i, r in enumerate(results):
        ticker = r["ticker"]
        bah    = r["bah"]
        base   = i * rows_per

        if strategy in ("momentum", "both"):
            ax = axes[base][0]
            ax.plot(bah.index, bah.values, label="B&H", color="steelblue", linewidth=1.2)
            eq = r["mom_res"]["equity"]
            ax.plot(eq.index, eq.values,
                    label=f"Momentum ({config.LEVERAGE}x)", color=colors_mom[i % 4], linewidth=1.4)
            m = r["mom_m"]
            ax.set_title(f"{ticker} Momentum — CAGR {m['cagr']:.1%}, "
                         f"Sharpe {m['sharpe']:.2f}, MaxDD {m['max_dd']:.1%}", fontsize=9)
            ax.set_ylabel("Value ($)")
            ax.legend(fontsize=8); ax.grid(alpha=0.3)
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
            base += 1

        if strategy in ("mean_rev", "both"):
            ax = axes[base][0]
            ax.plot(bah.index, bah.values, label="B&H", color="steelblue", linewidth=1.2)
            eq = r["mr_res"]["equity"]
            ax.plot(eq.index, eq.values,
                    label="Mean-rev (1x)", color=colors_mr[i % 4], linewidth=1.4)
            m = r["mr_m"]
            ax.set_title(f"{ticker} Mean-rev — CAGR {m['cagr']:.1%}, "
                         f"Sharpe {m['sharpe']:.2f}, MaxDD {m['max_dd']:.1%}", fontsize=9)
            ax.set_ylabel("Value ($)")
            ax.legend(fontsize=8); ax.grid(alpha=0.3)
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
            base += 1

        # Leverage panel (momentum only)
        if strategy in ("momentum", "both"):
            ax = axes[base][0]
            lev = r["mom_res"]["leverage"]
            ax.fill_between(lev.index, lev.values, 1, step="post",
                            alpha=0.5, color=colors_mom[i % 4],
                            label=f"Margin ON ({config.LEVERAGE}x)")
            ax.axhline(1.0, color="gray", linewidth=0.8, linestyle="--")
            ax.set_ylabel("Leverage")
            ax.set_ylim(0.5, config.LEVERAGE + 0.3)
            ax.set_yticks([1.0, config.LEVERAGE])
            ax.set_yticklabels(["1x", f"{config.LEVERAGE}x"], fontsize=7)
            ax.legend(fontsize=7, loc="upper left"); ax.grid(alpha=0.3)

    fig.suptitle(f"Stock Backtest — {', '.join(r['ticker'] for r in results)}", fontsize=11)
    plt.tight_layout()

    from datetime import date as _date
    path = f"charts/backtest/stock_backtest_{_date.today()}.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to {path}")
    plt.show()


if __name__ == "__main__":
    args = sys.argv[1:]
    strategy = "both"
    if "--strategy" in args:
        idx = args.index("--strategy")
        strategy = args[idx + 1]
        args = [a for j, a in enumerate(args) if j != idx and j != idx + 1]

    tickers = [a.upper() for a in args] if args else ["NVDA", "MSFT", "AAPL"]

    print(f"Backtesting: {', '.join(tickers)}  |  strategy: {strategy}")
    results = [r for t in tickers if (r := backtest(t, strategy)) is not None]
    if results:
        plot(results, strategy)
