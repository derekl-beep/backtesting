"""
Portfolio backtest: multiple ETFs with fixed weights, independent MA signals.

Each ETF can have its own MA params — run `python -m tools.optimize <TICKER>`
to find optimal params before updating the config below.

Usage:
  python -m tools.portfolio                               # default portfolio
  python -m tools.portfolio SPMO:0.5:50:100 VGT:0.3:20:100 VOO:0.2:30:150
    format: TICKER:weight:ma_fast:ma_slow
"""

import sys
import pandas as pd
import matplotlib.pyplot as plt

from core import config
from core.data import fetch
from core.metrics import calc
from core.simulator import run as simulate
from signals import ma as sig_ma
from strategies import momentum

# Per-ticker config: (weight, ma_fast, ma_slow)
# Each ticker's MA params validated independently via walk-forward (2022-2025 OOS folds).
DEFAULT_PORTFOLIO = {
    "SPMO": (0.80, 50, 100),   # 3/4 folds, avg +12.5% vs B&H
    "GLD":  (0.20, 30,  50),   # 4/4 folds, avg +17.7% vs B&H
}


def _run_leg(ticker: str, weight: float, ma_fast: int, ma_slow: int) -> dict | None:
    prices = fetch(ticker)
    if len(prices) < ma_slow + 10:
        print(f"{ticker}: not enough data.")
        return None

    capital = config.INITIAL_CAPITAL * weight
    sig = sig_ma.signal(prices, ma_fast, ma_slow)
    pos = momentum.positions(sig)
    result = simulate(prices, pos, capital=capital)

    bah_prices = prices.reindex(result["equity"].index)
    bah_equity = capital * (bah_prices / bah_prices.iloc[0])

    return {
        "ticker":    ticker,
        "weight":    weight,
        "ma_fast":   ma_fast,
        "ma_slow":   ma_slow,
        "bah":       bah_equity,
        "equity":    result["equity"],
        "leverage":  result["leverage"],
        "margin_calls": result["margin_calls"],
        "total_fees":   result["total_fees"],
    }


def backtest(portfolio: dict) -> None:
    legs = []
    for ticker, (weight, ma_fast, ma_slow) in portfolio.items():
        print(f"Fetching {ticker}...")
        leg = _run_leg(ticker, weight, ma_fast, ma_slow)
        if leg:
            legs.append(leg)

    if not legs:
        return

    # Align all legs to common trading dates
    common_idx = legs[0]["equity"].index
    for leg in legs[1:]:
        common_idx = common_idx.intersection(leg["equity"].index)

    portfolio_equity = sum(leg["equity"].reindex(common_idx) for leg in legs)
    blended_bah      = sum(leg["bah"].reindex(common_idx) for leg in legs)

    _print_per_leg(legs, common_idx)
    _print_aggregate(legs, portfolio_equity, blended_bah)
    _print_yearly(blended_bah, portfolio_equity)
    plot(legs, portfolio_equity, blended_bah, common_idx)


def _print_per_leg(legs, common_idx):
    print(f"\n{'='*60}")
    print(f" Per-leg performance")
    print(f"{'='*60}")
    print(f"  {'Ticker':<8} {'Weight':>7} {'Params':<12} {'B&H CAGR':>9} "
          f"{'Strat CAGR':>11} {'Sharpe':>7} {'MaxDD':>7} {'Fees':>8}")
    print(f"  {'-'*8} {'-'*7} {'-'*12} {'-'*9} {'-'*11} {'-'*7} {'-'*7} {'-'*8}")
    for leg in legs:
        bah_m   = calc(leg["bah"].reindex(common_idx))
        strat_m = calc(leg["equity"].reindex(common_idx))
        params  = f"MA{leg['ma_fast']}/{leg['ma_slow']}"
        print(f"  {leg['ticker']:<8} {leg['weight']:>7.0%} {params:<12} "
              f"{bah_m['cagr']:>9.1%} {strat_m['cagr']:>11.1%} "
              f"{strat_m['sharpe']:>7.2f} {strat_m['max_dd']:>7.1%} "
              f"${leg['total_fees']:>7,.2f}")


def _print_aggregate(legs, portfolio_equity, blended_bah):
    port_m = calc(portfolio_equity)
    bah_m  = calc(blended_bah)
    total_fees         = sum(leg["total_fees"] for leg in legs)
    total_margin_calls = sum(leg["margin_calls"] for leg in legs)

    print(f"\n{'='*60}")
    print(f" Portfolio aggregate")
    print(f"{'='*60}")
    print(f"  {'':30s} {'Blended B&H':>12} {'Portfolio':>10}")
    print(f"  {'Total return':30s} {bah_m['total']:>12.1%} {port_m['total']:>10.1%}")
    print(f"  {'CAGR':30s} {bah_m['cagr']:>12.1%} {port_m['cagr']:>10.1%}")
    print(f"  {'Sharpe ratio':30s} {bah_m['sharpe']:>12.2f} {port_m['sharpe']:>10.2f}")
    print(f"  {'Max drawdown':30s} {bah_m['max_dd']:>12.1%} {port_m['max_dd']:>10.1%}")
    print(f"  {'Total fees':30s} {'':>12} ${total_fees:>9,.2f}")
    print(f"  {'Margin calls (total)':30s} {'':>12} {total_margin_calls:>10}")


def _print_yearly(bah, portfolio):
    years = sorted(set(bah.index.year))
    print(f"\n  {'Year':<6} {'B&H':>8} {'Portfolio':>10} {'vs B&H':>8} {'MaxDD':>8}")
    print(f"  {'-'*6} {'-'*8} {'-'*10} {'-'*8} {'-'*8}")
    for yr in years:
        b = bah[bah.index.year == yr]
        p = portfolio[portfolio.index.year == yr]
        if len(b) < 2 or len(p) < 2:
            continue
        bah_ret  = b.iloc[-1] / b.iloc[0] - 1
        port_ret = p.iloc[-1] / p.iloc[0] - 1
        max_dd   = ((p / p.cummax()) - 1).min()
        diff     = port_ret - bah_ret
        print(f"  {yr:<6} {bah_ret:>8.1%} {port_ret:>10.1%} {diff:>+8.1%} {max_dd:>8.1%}")


_LEG_COLORS = ["darkorange", "green", "crimson", "purple", "brown", "teal"]


def plot(legs, portfolio_equity, blended_bah, common_idx):
    fig, (ax_eq, ax_lev) = plt.subplots(
        2, 1, figsize=(13, 10), gridspec_kw={"height_ratios": [3, 1]}
    )

    # Equity panel
    ax_eq.plot(blended_bah.index, blended_bah.values,
               label="Blended B&H", color="steelblue", linewidth=1.5, linestyle="--")
    ax_eq.plot(portfolio_equity.index, portfolio_equity.values,
               label="Portfolio Strategy", color="black", linewidth=2)
    for i, leg in enumerate(legs):
        color = _LEG_COLORS[i % len(_LEG_COLORS)]
        eq = leg["equity"].reindex(common_idx)
        ax_eq.plot(eq.index, eq.values,
                   label=f"{leg['ticker']} ({leg['weight']:.0%}, MA{leg['ma_fast']}/{leg['ma_slow']})",
                   color=color, linewidth=1, alpha=0.6)

    port_m = calc(portfolio_equity)
    bah_m  = calc(blended_bah)
    ax_eq.set_title(
        f"B&H: CAGR {bah_m['cagr']:.1%}, Sharpe {bah_m['sharpe']:.2f}, MaxDD {bah_m['max_dd']:.1%}"
        f"   |   Portfolio: CAGR {port_m['cagr']:.1%}, Sharpe {port_m['sharpe']:.2f}, "
        f"MaxDD {port_m['max_dd']:.1%}", fontsize=9)
    ax_eq.set_ylabel("Portfolio Value ($)")
    ax_eq.legend(fontsize=9)
    ax_eq.grid(alpha=0.3)
    ax_eq.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # Leveraged-weight stacked panel
    accumulated = pd.Series(0.0, index=common_idx)
    for i, leg in enumerate(legs):
        color    = _LEG_COLORS[i % len(_LEG_COLORS)]
        lev      = leg["leverage"].reindex(common_idx)
        is_levd  = (lev >= config.LEVERAGE).astype(float) * leg["weight"]
        bottom   = accumulated.values
        top      = (accumulated + is_levd).values
        ax_lev.fill_between(common_idx, bottom, top,
                            alpha=0.5, color=color, label=f"{leg['ticker']} margin ON")
        accumulated = accumulated + is_levd

    ax_lev.set_ylabel("Portfolio weight\nin margin")
    ax_lev.set_ylim(0, 1.05)
    ax_lev.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
    ax_lev.legend(fontsize=8)
    ax_lev.grid(alpha=0.3)

    alloc = ", ".join(f"{leg['ticker']} {leg['weight']:.0%}" for leg in legs)
    fig.suptitle(
        f"Portfolio: {alloc} | {config.LEVERAGE}x margin, {config.MARGIN_RATE:.1%} borrow",
        fontsize=11)

    plt.tight_layout()
    plt.savefig("portfolio_results.png", dpi=150, bbox_inches="tight")
    print("\nChart saved to portfolio_results.png")
    plt.show()


def _parse_args(args: list[str]) -> dict:
    portfolio = {}
    for arg in args:
        parts = arg.split(":")
        if len(parts) != 4:
            print(f"Bad arg '{arg}' — expected TICKER:weight:ma_fast:ma_slow")
            sys.exit(1)
        ticker, weight, ma_fast, ma_slow = parts
        portfolio[ticker.upper()] = (float(weight), int(ma_fast), int(ma_slow))
    total = sum(w for w, _, _ in portfolio.values())
    if abs(total - 1.0) > 0.01:
        print(f"Weights sum to {total:.2%}, expected 100%.")
        sys.exit(1)
    return portfolio


if __name__ == "__main__":
    portfolio = _parse_args(sys.argv[1:]) if sys.argv[1:] else DEFAULT_PORTFOLIO
    backtest(portfolio)
