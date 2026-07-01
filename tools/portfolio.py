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
import matplotlib
matplotlib.use("Agg")
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

from core.portfolio_config import PORTFOLIO as DEFAULT_PORTFOLIO, MACD_PARAMS


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
    from datetime import date as _date
    path = f"charts/portfolio/portfolio_results_{_date.today()}.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to {path}")
    plt.close()


def backtest_dynamic(portfolio: dict, driver: str = "SPMO") -> None:
    """
    Compare fixed-weight portfolio vs dynamic allocation:
    bull weights (from portfolio config) when driver signal is ON,
    bear weight configs (GLD-heavy) when driver signal is OFF.

    Tests three bear configs: 60/40, 40/60, 20/80 SPMO/GLD.
    """
    print(f"Fetching legs...")
    legs = {}
    for ticker, cfg in portfolio.items():
        leg = _run_leg(ticker, {**cfg, "weight": 1.0})
        if leg:
            legs[ticker] = leg

    if not legs:
        return

    # Align to common index
    common_idx = list(legs.values())[0]["equity"].index
    for leg in legs.values():
        common_idx = common_idx.intersection(leg["equity"].index)

    # Normalised daily returns per leg (strategy returns, weight-independent)
    rets = {t: leg["equity"].reindex(common_idx).pct_change().fillna(0)
            for t, leg in legs.items()}

    # Driver signal on common index
    driver_cfg = portfolio.get(driver, list(portfolio.values())[0])
    driver_prices = fetch(driver)
    driver_sig = sig_ma.signal(driver_prices, driver_cfg["ma_fast"], driver_cfg["ma_slow"])
    driver_sig = driver_sig.reindex(common_idx).ffill().fillna(0)

    # Bull weights from portfolio config
    bull_w = {t: portfolio[t]["weight"] for t in legs}

    # Bear configs to test
    tickers = list(legs.keys())   # assumes 2-asset portfolio: SPMO, GLD
    if len(tickers) == 2:
        t0, t1 = tickers
        bear_configs = {
            f"bear→ {t0} 60% / {t1} 40%": {t0: 0.60, t1: 0.40},
            f"bear→ {t0} 40% / {t1} 60%": {t0: 0.40, t1: 0.60},
            f"bear→ {t0} 20% / {t1} 80%": {t0: 0.20, t1: 0.80},
        }
    else:
        print("Dynamic mode supports 2-asset portfolios only.")
        return

    def _portfolio_equity(weight_fn):
        daily = sum(weight_fn(t) * rets[t] for t in legs)
        return config.INITIAL_CAPITAL * (1 + daily).cumprod()

    static_eq = _portfolio_equity(lambda t: bull_w[t])

    # B&H baseline
    bah_eq = sum(
        bull_w[t] * config.INITIAL_CAPITAL
        * (legs[t]["bah"].reindex(common_idx) / legs[t]["bah"].reindex(common_idx).iloc[0])
        for t in legs
    )

    print(f"\n{'='*72}")
    print(f"  Dynamic allocation — driver: {driver}  "
          f"(bull={'/'.join(f'{t} {bull_w[t]:.0%}' for t in legs)})")
    print(f"{'='*72}")
    print(f"  {'Config':<36} {'CAGR':>7} {'Sharpe':>7} {'MaxDD':>7} {'vs static':>10}")
    print(f"  {'-'*36} {'-'*7} {'-'*7} {'-'*7} {'-'*10}")

    static_m = calc(static_eq)
    print(f"  {'Static (current)':<36} {static_m['cagr']:>7.1%} "
          f"{static_m['sharpe']:>7.2f} {static_m['max_dd']:>7.1%} {'—':>10}")

    dynamic_equities = {}
    for label, bear_w in bear_configs.items():
        def _dyn_weight(t, bw=bear_w):
            bull_days  = driver_sig * bull_w[t]
            bear_days  = (1 - driver_sig) * bw.get(t, 0)
            return bull_days + bear_days

        daily = sum(_dyn_weight(t) * rets[t] for t in legs)
        eq = config.INITIAL_CAPITAL * (1 + daily).cumprod()
        m  = calc(eq)
        vs = m["cagr"] - static_m["cagr"]
        print(f"  {label:<36} {m['cagr']:>7.1%} {m['sharpe']:>7.2f} "
              f"{m['max_dd']:>7.1%} {vs:>+10.1%}")
        dynamic_equities[label] = eq

    # Year-by-year for best dynamic config
    best_label = max(dynamic_equities, key=lambda k: calc(dynamic_equities[k])["sharpe"])
    best_eq    = dynamic_equities[best_label]
    print(f"\n  Year-by-year: Static vs best dynamic ({best_label.strip()})")
    print(f"  {'Year':<6} {'B&H':>8} {'Static':>8} {'Dynamic':>9} {'Δ CAGR':>8}")
    print(f"  {'-'*6} {'-'*8} {'-'*8} {'-'*9} {'-'*8}")
    for yr in sorted(set(common_idx.year)):
        mask = common_idx.year == yr
        b = bah_eq[mask];  s = static_eq[mask];  d = best_eq[mask]
        if len(b) < 2: continue
        br = b.iloc[-1]/b.iloc[0]-1; sr = s.iloc[-1]/s.iloc[0]-1; dr = d.iloc[-1]/d.iloc[0]-1
        print(f"  {yr:<6} {br:>8.1%} {sr:>8.1%} {dr:>9.1%} {dr-sr:>+8.1%}")

    # Plot
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.plot(bah_eq.index, bah_eq.values, label="B&H 1x", color="steelblue",
            linewidth=1.2, linestyle="--")
    ax.plot(static_eq.index, static_eq.values, label="Static 80/20", color="black",
            linewidth=1.8)
    colors = ["darkorange", "green", "crimson"]
    for (label, eq), color in zip(dynamic_equities.items(), colors):
        ax.plot(eq.index, eq.values, label=label, color=color, linewidth=1.2, alpha=0.85)
    ax.set_title(f"Dynamic GLD allocation — driver: {driver}", fontsize=10)
    ax.set_ylabel("Portfolio Value ($)")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    plt.tight_layout()
    from datetime import date as _date
    path = f"charts/portfolio/portfolio_dynamic_{_date.today()}.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to {path}")
    plt.close()


def backtest_dynamic_oos(portfolio: dict, driver: str = "SPMO") -> None:
    """
    Walk-forward OOS validation of dynamic GLD allocation.
    Tests each year (2022–present) independently — no training phase since
    there are no free parameters; the rule is fixed (shift to GLD when bearish).
    Shows whether dynamic beats static consistently across folds.
    """
    BEAR_CONFIGS = {
        "60/40": {list(portfolio.keys())[0]: 0.60, list(portfolio.keys())[1]: 0.40},
        "40/60": {list(portfolio.keys())[0]: 0.40, list(portfolio.keys())[1]: 0.60},
        "20/80": {list(portfolio.keys())[0]: 0.20, list(portfolio.keys())[1]: 0.80},
    }
    FIRST_TEST_YEAR = 2022

    print("Fetching legs...")
    legs = {}
    for ticker, cfg in portfolio.items():
        leg = _run_leg(ticker, {**cfg, "weight": 1.0})
        if leg:
            legs[ticker] = leg

    if len(legs) != 2:
        print("Dynamic OOS supports 2-asset portfolios only.")
        return

    t0, t1 = list(legs.keys())
    bull_w = {t0: portfolio[t0]["weight"], t1: portfolio[t1]["weight"]}

    # Full aligned index
    common_idx = legs[t0]["equity"].index.intersection(legs[t1]["equity"].index)
    rets = {t: legs[t]["equity"].reindex(common_idx).pct_change().fillna(0)
            for t in legs}

    # Driver signal
    driver_cfg = portfolio[driver]
    driver_sig = sig_ma.signal(fetch(driver), driver_cfg["ma_fast"], driver_cfg["ma_slow"])
    driver_sig = driver_sig.reindex(common_idx).ffill().fillna(0)

    def _equity(weight_fn):
        daily = sum(weight_fn(t) * rets[t] for t in legs)
        return config.INITIAL_CAPITAL * (1 + daily).cumprod()

    static_eq = _equity(lambda t: bull_w[t])

    def _dynamic_eq(bear_w):
        bull_days = driver_sig
        bear_days = 1 - driver_sig
        wt = {t: bull_days * bull_w[t] + bear_days * bear_w.get(t, 0) for t in legs}
        return _equity(lambda t: wt[t])

    dynamic_eqs = {label: _dynamic_eq(bw) for label, bw in BEAR_CONFIGS.items()}

    current_year = pd.Timestamp.now().year
    fold_years   = range(FIRST_TEST_YEAR, current_year + 1)

    print(f"\n{'='*78}")
    print(f"  Dynamic allocation OOS validation  (driver: {driver}, "
          f"bull={t0} {bull_w[t0]:.0%}/{t1} {bull_w[t1]:.0%})")
    print(f"{'='*78}")

    col_w = 10
    headers = ["Static"] + [f"Dyn {k}" for k in BEAR_CONFIGS]
    print(f"  {'Fold':<8}" + "".join(f"{h:>{col_w}}" for h in headers))
    print(f"  {'-'*8}" + f"{'-'*col_w}" * len(headers))

    wins = {label: 0 for label in BEAR_CONFIGS}
    n_folds = 0

    for yr in fold_years:
        mask = common_idx.year == yr
        if mask.sum() < 10:
            continue
        n_folds += 1

        def _yr_ret(eq):
            s = eq[mask]
            return s.iloc[-1] / s.iloc[0] - 1

        static_ret = _yr_ret(static_eq)
        row = f"  {yr:<8}{static_ret:>{col_w}.1%}"
        for label, deq in dynamic_eqs.items():
            dr = _yr_ret(deq)
            marker = " ✓" if dr > static_ret else "  "
            row += f"{dr:>{col_w-2}.1%}{marker}"
            if dr > static_ret:
                wins[label] += 1
        print(row)

    print(f"\n  Win rate vs static ({n_folds} folds):")
    for label, w in wins.items():
        bear_w = BEAR_CONFIGS[label]
        print(f"    bear {label} ({t0} {bear_w[t0]:.0%}/{t1} {bear_w[t1]:.0%}): "
              f"{w}/{n_folds} folds  ({w/n_folds:.0%})")

    # Full-period summary
    print(f"\n  Full-period summary (2020–present):")
    print(f"  {'Config':<24} {'CAGR':>7} {'Sharpe':>7} {'MaxDD':>7} {'vs static':>10}")
    print(f"  {'-'*24} {'-'*7} {'-'*7} {'-'*7} {'-'*10}")
    sm = calc(static_eq)
    print(f"  {'Static':<24} {sm['cagr']:>7.1%} {sm['sharpe']:>7.2f} {sm['max_dd']:>7.1%} {'—':>10}")
    for label, deq in dynamic_eqs.items():
        dm = calc(deq)
        vs = dm["cagr"] - sm["cagr"]
        print(f"  {f'Dynamic bear {label}':<24} {dm['cagr']:>7.1%} {dm['sharpe']:>7.2f} "
              f"{dm['max_dd']:>7.1%} {vs:>+10.1%}")


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
    args = sys.argv[1:]
    dynamic = "--dynamic" in args
    oos     = "--oos" in args
    args = [a for a in args if a not in ("--dynamic", "--oos")]

    portfolio = _parse_args(args) if args else DEFAULT_PORTFOLIO

    if dynamic and oos:
        backtest_dynamic_oos(portfolio)
    elif dynamic:
        backtest_dynamic(portfolio)
    else:
        backtest(portfolio)
