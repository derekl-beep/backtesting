"""
Portfolio backtest: multiple ETFs with fixed weights, independent signals.

Each ETF has its own signal config validated via walk-forward optimization.
Run `python -m tools.optimize [--signals ma,rsi,macd] <TICKER>` to tune.

Usage:
  python -m tools.portfolio                               # default portfolio
  python -m tools.portfolio SPMO:0.8:30:100 GLD:0.2:30:50
    format: TICKER:weight:ma_fast:ma_slow  (MA-only via CLI)
"""

import sys
import pandas as pd
import matplotlib.pyplot as plt

from core import config
from core.data import fetch
from core.metrics import calc
from core.simulator import run as simulate
from signals import ma as sig_ma
from signals import rsi as sig_rsi
from signals import macd as sig_macd
from signals.combo import majority_of
from strategies import momentum

# Per-ticker config: weight + signal params validated via walk-forward (2022-2025 OOS folds).
DEFAULT_PORTFOLIO = {
    #          weight  ma_fast  ma_slow
    "SPMO": dict(weight=0.80, ma_fast=50, ma_slow=100),   # 3/4 folds, avg +12.5% vs B&H; MA-only beats MA+RSI/MACD after fees
    "GLD":  dict(weight=0.20, ma_fast=30, ma_slow=50),    # 4/4 folds, avg +17.7% vs B&H
}

MACD_PARAMS = (12, 26, 9)


def _build_signal(prices, cfg: dict):
    parts = [sig_ma.signal(prices, cfg["ma_fast"], cfg["ma_slow"])]
    if cfg.get("rsi"):
        parts.append(sig_rsi.signal(prices, threshold=cfg["rsi"]))
    if cfg.get("macd"):
        parts.append(sig_macd.signal(prices, *MACD_PARAMS))
    return parts[0] if len(parts) == 1 else majority_of(parts)


def _param_label(cfg: dict) -> str:
    label = f"MA{cfg['ma_fast']}/{cfg['ma_slow']}"
    if cfg.get("rsi"):
        label += f" RSI>{cfg['rsi']}"
    if cfg.get("macd"):
        label += " MACD"
    return label


def _run_leg(ticker: str, cfg: dict) -> dict | None:
    prices = fetch(ticker)
    if len(prices) < cfg["ma_slow"] + 10:
        print(f"{ticker}: not enough data.")
        return None

    capital = config.INITIAL_CAPITAL * cfg["weight"]
    sig     = _build_signal(prices, cfg)
    pos     = momentum.positions(sig)
    result  = simulate(prices, pos, capital=capital)

    bah_prices = prices.reindex(result["equity"].index)
    bah_equity = capital * (bah_prices / bah_prices.iloc[0])

    return {
        "ticker":       ticker,
        "weight":       cfg["weight"],
        "label":        _param_label(cfg),
        "bah":          bah_equity,
        "equity":       result["equity"],
        "leverage":     result["leverage"],
        "margin_calls": result["margin_calls"],
        "total_fees":   result["total_fees"],
    }


def _run_leg_2x(ticker: str, cfg: dict):
    """Simulate naive 2x B&H (always leveraged, no signal) for a leg."""
    prices = fetch(ticker)
    if len(prices) < cfg["ma_slow"] + 10:
        return None
    # Match the same start date as the signal leg (after MA warmup)
    sig    = _build_signal(prices, cfg)
    always = pd.Series(config.LEVERAGE, index=sig.index)
    result = simulate(prices, always, capital=config.INITIAL_CAPITAL * cfg["weight"])
    return result["equity"]


def backtest(portfolio: dict) -> None:
    legs = []
    for ticker, cfg in portfolio.items():
        print(f"Fetching {ticker}...")
        leg = _run_leg(ticker, cfg)
        if leg:
            legs.append(leg)

    if not legs:
        return

    common_idx      = legs[0]["equity"].index
    for leg in legs[1:]:
        common_idx  = common_idx.intersection(leg["equity"].index)

    portfolio_equity = sum(leg["equity"].reindex(common_idx) for leg in legs)
    blended_bah      = sum(leg["bah"].reindex(common_idx) for leg in legs)

    # Naive 2x B&H: always leveraged, no signal
    bah_2x_legs = [_run_leg_2x(t, cfg) for t, cfg in portfolio.items()]
    blended_bah_2x = sum(e.reindex(common_idx) for e in bah_2x_legs if e is not None)

    _print_per_leg(legs, common_idx)
    _print_aggregate(legs, portfolio_equity, blended_bah, blended_bah_2x)
    _print_yearly(blended_bah, portfolio_equity, blended_bah_2x)
    plot(legs, portfolio_equity, blended_bah, blended_bah_2x, common_idx)


def _print_per_leg(legs, common_idx):
    w = max(len(leg["label"]) for leg in legs) + 2
    print(f"\n{'='*70}")
    print(f" Per-leg performance")
    print(f"{'='*70}")
    print(f"  {'Ticker':<8} {'Weight':>7} {'Signal':<{w}} {'B&H CAGR':>9} "
          f"{'Strat CAGR':>11} {'Sharpe':>7} {'MaxDD':>7} {'Fees':>8}")
    print(f"  {'-'*8} {'-'*7} {'-'*w} {'-'*9} {'-'*11} {'-'*7} {'-'*7} {'-'*8}")
    for leg in legs:
        bah_m   = calc(leg["bah"].reindex(common_idx))
        strat_m = calc(leg["equity"].reindex(common_idx))
        print(f"  {leg['ticker']:<8} {leg['weight']:>7.0%} {leg['label']:<{w}} "
              f"{bah_m['cagr']:>9.1%} {strat_m['cagr']:>11.1%} "
              f"{strat_m['sharpe']:>7.2f} {strat_m['max_dd']:>7.1%} "
              f"${leg['total_fees']:>7,.2f}")


def _print_aggregate(legs, portfolio_equity, blended_bah, blended_bah_2x):
    port_m  = calc(portfolio_equity)
    bah_m   = calc(blended_bah)
    bah2x_m = calc(blended_bah_2x)
    total_fees         = sum(leg["total_fees"] for leg in legs)
    total_margin_calls = sum(leg["margin_calls"] for leg in legs)

    print(f"\n{'='*70}")
    print(f" Portfolio aggregate")
    print(f"{'='*70}")
    print(f"  {'':30s} {'B&H 1x':>10} {'B&H 2x':>10} {'Strategy':>10}")
    print(f"  {'Total return':30s} {bah_m['total']:>10.1%} {bah2x_m['total']:>10.1%} {port_m['total']:>10.1%}")
    print(f"  {'CAGR':30s} {bah_m['cagr']:>10.1%} {bah2x_m['cagr']:>10.1%} {port_m['cagr']:>10.1%}")
    print(f"  {'Sharpe ratio':30s} {bah_m['sharpe']:>10.2f} {bah2x_m['sharpe']:>10.2f} {port_m['sharpe']:>10.2f}")
    print(f"  {'Max drawdown':30s} {bah_m['max_dd']:>10.1%} {bah2x_m['max_dd']:>10.1%} {port_m['max_dd']:>10.1%}")
    print(f"  {'Total fees':30s} {'':>10} {'':>10} ${total_fees:>9,.2f}")
    print(f"  {'Margin calls (total)':30s} {'':>10} {'':>10} {total_margin_calls:>10}")


def _print_yearly(bah, portfolio, bah_2x):
    years = sorted(set(bah.index.year))
    print(f"\n  {'Year':<6} {'B&H 1x':>8} {'B&H 2x':>8} {'Strategy':>10} {'vs 1x':>7} {'vs 2x':>7} {'MaxDD':>8}")
    print(f"  {'-'*6} {'-'*8} {'-'*8} {'-'*10} {'-'*7} {'-'*7} {'-'*8}")
    for yr in years:
        b  = bah[bah.index.year == yr]
        b2 = bah_2x[bah_2x.index.year == yr]
        p  = portfolio[portfolio.index.year == yr]
        if len(b) < 2 or len(p) < 2:
            continue
        bah_ret   = b.iloc[-1] / b.iloc[0] - 1
        bah2x_ret = b2.iloc[-1] / b2.iloc[0] - 1 if len(b2) >= 2 else float("nan")
        port_ret  = p.iloc[-1] / p.iloc[0] - 1
        max_dd    = ((p / p.cummax()) - 1).min()
        print(f"  {yr:<6} {bah_ret:>8.1%} {bah2x_ret:>8.1%} {port_ret:>10.1%} "
              f"{port_ret - bah_ret:>+7.1%} {port_ret - bah2x_ret:>+7.1%} {max_dd:>8.1%}")


_LEG_COLORS = ["darkorange", "green", "crimson", "purple", "brown", "teal"]


def plot(legs, portfolio_equity, blended_bah, blended_bah_2x, common_idx):
    fig, (ax_eq, ax_lev) = plt.subplots(
        2, 1, figsize=(13, 10), gridspec_kw={"height_ratios": [3, 1]}
    )

    ax_eq.plot(blended_bah.index, blended_bah.values,
               label="Blended B&H 1x", color="steelblue", linewidth=1.5, linestyle="--")
    ax_eq.plot(blended_bah_2x.index, blended_bah_2x.values,
               label="Blended B&H 2x", color="mediumpurple", linewidth=1.5, linestyle="--")
    ax_eq.plot(portfolio_equity.index, portfolio_equity.values,
               label="Portfolio Strategy", color="black", linewidth=2)
    for i, leg in enumerate(legs):
        color = _LEG_COLORS[i % len(_LEG_COLORS)]
        eq = leg["equity"].reindex(common_idx)
        ax_eq.plot(eq.index, eq.values,
                   label=f"{leg['ticker']} ({leg['weight']:.0%}, {leg['label']})",
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

    accumulated = pd.Series(0.0, index=common_idx)
    for i, leg in enumerate(legs):
        color   = _LEG_COLORS[i % len(_LEG_COLORS)]
        lev     = leg["leverage"].reindex(common_idx)
        is_levd = (lev >= config.LEVERAGE).astype(float) * leg["weight"]
        bottom  = accumulated.values
        top     = (accumulated + is_levd).values
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
    plt.savefig("charts/portfolio_results.png", dpi=150, bbox_inches="tight")
    print("\nChart saved to charts/portfolio_results.png")
    plt.show()


def _parse_args(args: list[str]) -> dict:
    portfolio = {}
    for arg in args:
        parts = arg.split(":")
        if len(parts) != 4:
            print(f"Bad arg '{arg}' — expected TICKER:weight:ma_fast:ma_slow")
            sys.exit(1)
        ticker, weight, ma_fast, ma_slow = parts
        portfolio[ticker.upper()] = dict(
            weight=float(weight), ma_fast=int(ma_fast), ma_slow=int(ma_slow)
        )
    total = sum(cfg["weight"] for cfg in portfolio.values())
    if abs(total - 1.0) > 0.01:
        print(f"Weights sum to {total:.2%}, expected 100%.")
        sys.exit(1)
    return portfolio


if __name__ == "__main__":
    portfolio = _parse_args(sys.argv[1:]) if sys.argv[1:] else DEFAULT_PORTFOLIO
    backtest(portfolio)
