"""
Backtest individual stocks with strategy selection.

Strategies:
  momentum     — MA50/100 crossover, 2x when bullish, 1x when bearish
  momentum_3t  — MA fast/mid/200 three-tier, 2x/1x/cash (use --ma fast:mid)
  mean_rev     — RSI band (14/30/70), 1x when oversold, cash otherwise
  both         — momentum vs mean_rev side-by-side (default)
  compare      — momentum (2-tier) vs momentum_3t side-by-side

Usage:
  python -m tools.stock_backtest NVDA
  python -m tools.stock_backtest NVDA MSFT AAPL
  python -m tools.stock_backtest NVDA --strategy momentum
  python -m tools.stock_backtest NVDA --strategy mean_rev
  python -m tools.stock_backtest NVDA --strategy momentum_3t --ma 20:75
  python -m tools.stock_backtest NVDA --strategy compare --ma 20:75
"""

import sys
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core import config
from core.data import fetch
from core.metrics import calc
from core.simulator import run as simulate
from signals import ma as sig_ma
from signals import ma_3tier as sig_ma3t
from signals import rsi_band as sig_rsi_band
from strategies import momentum as strat_momentum
from strategies import momentum_3t as strat_3t
from strategies import mean_reversion as strat_mr

MOM_FAST  = 50
MOM_SLOW  = 100
MOM_SLOW3 = 200
MR_PERIOD = 14
MR_OS     = 30
MR_OB     = 70


def _bah(prices, index):
    p = prices.reindex(index)
    return config.INITIAL_CAPITAL * (p / p.iloc[0])


def _run_momentum(prices):
    sig    = sig_ma.signal(prices, MOM_FAST, MOM_SLOW)
    pos    = strat_momentum.positions(sig)
    result = simulate(prices, pos)
    return result, _bah(prices, result["equity"].index)


def _run_momentum_3t(prices, fast, mid, slow):
    sig    = sig_ma3t.signal(prices, fast, mid, slow)
    pos    = strat_3t.positions(sig)
    result = simulate(prices, pos)
    return result, _bah(prices, result["equity"].index)


def _run_mean_rev(prices):
    sig    = sig_rsi_band.signal(prices, MR_PERIOD, MR_OS, MR_OB)
    pos    = strat_mr.positions(sig)
    result = simulate(prices, pos)
    return result, _bah(prices, result["equity"].index)


def backtest(ticker: str, strategy: str = "both",
             fast: int = 20, mid: int = 75, slow: int = MOM_SLOW3) -> dict | None:
    prices = fetch(ticker)
    if len(prices) < slow + 10:
        print(f"{ticker}: not enough data.")
        return None

    r = {"ticker": ticker, "strategy": strategy, "fast": fast, "mid": mid, "slow": slow}

    if strategy in ("momentum", "both", "compare"):
        res, bah   = _run_momentum(prices)
        r["mom_res"] = res
        r["mom_m"]   = calc(res["equity"])
        r["bah"]     = bah
        r["bah_m"]   = calc(bah)

    if strategy in ("momentum_3t", "compare"):
        res, bah   = _run_momentum_3t(prices, fast, mid, slow)
        r["3t_res"]  = res
        r["3t_m"]    = calc(res["equity"])
        if "bah_m" not in r:
            r["bah"]   = bah
            r["bah_m"] = calc(bah)

    if strategy in ("mean_rev", "both"):
        res, bah   = _run_mean_rev(prices)
        r["mr_res"]  = res
        r["mr_m"]    = calc(res["equity"])
        if "bah_m" not in r:
            r["bah"]   = bah
            r["bah_m"] = calc(bah)

    _print_results(r)
    return r


def _col_labels(strategy, fast, mid, slow):
    return {
        "momentum":    ["Momentum"],
        "momentum_3t": [f"3T {fast}/{mid}/{slow}"],
        "mean_rev":    ["Mean-rev"],
        "both":        ["Momentum", "Mean-rev"],
        "compare":     ["Momentum", f"3T {fast}/{mid}/{slow}"],
    }[strategy]


def _res_keys(strategy):
    return {
        "momentum":    ["mom_m"],
        "momentum_3t": ["3t_m"],
        "mean_rev":    ["mr_m"],
        "both":        ["mom_m", "mr_m"],
        "compare":     ["mom_m", "3t_m"],
    }[strategy]


def _sim_result(r, metric_key):
    return {"mom_m": r.get("mom_res"), "3t_m": r.get("3t_res"), "mr_m": r.get("mr_res")}[metric_key]


def _print_results(r):
    strategy = r["strategy"]
    bah_m    = r["bah_m"]
    rkeys    = _res_keys(strategy)
    cols     = _col_labels(strategy, r["fast"], r["mid"], r["slow"])

    print(f"\n{'='*70}")
    print(f" {r['ticker']}")
    print(f"{'='*70}")
    print(f"  {'':30s} {'B&H':>10}" + "".join(f" {c:>14}" for c in cols))

    for label, key, fmt in [
        ("Total return", "total",  ".1%"),
        ("CAGR",         "cagr",   ".1%"),
        ("Sharpe ratio", "sharpe", ".2f"),
        ("Max drawdown", "max_dd", ".1%"),
    ]:
        row = f"  {label:30s} {bah_m[key]:>10{fmt}}"
        for rk in rkeys:
            row += f" {r[rk][key]:>14{fmt}}"
        print(row)

    # Fees / margin calls — one row per strategy column
    for rk, col in zip(rkeys, cols):
        obj = _sim_result(r, rk)
        if obj:
            print(f"  {f'Margin calls ({col})':30s} {'':>10} {obj['margin_calls']:>14}")
            print(f"  {f'Total fees ({col})':30s} {'':>10} ${obj['total_fees']:>13,.2f}")

    _print_yearly(r)


def _print_yearly(r):
    strategy = r["strategy"]
    bah      = r["bah"]
    rkeys    = _res_keys(strategy)
    cols     = _col_labels(strategy, r["fast"], r["mid"], r["slow"])

    idx = bah.index
    for rk in rkeys:
        obj = _sim_result(r, rk)
        if obj is not None:
            idx = idx.intersection(obj["equity"].index)

    bah = bah.reindex(idx)

    header = f"\n  {'Year':<6} {'B&H':>8}"
    for col in cols:
        header += f" {col:>14} {'vs B&H':>8}"
    print(header)
    print(f"  {'-'*6} {'-'*8}" + f" {'-'*14} {'-'*8}" * len(cols))

    for yr in sorted(set(idx.year)):
        mask    = idx.year == yr
        b       = bah[mask]
        if len(b) < 2:
            continue
        bah_ret = b.iloc[-1] / b.iloc[0] - 1
        row     = f"  {yr:<6} {bah_ret:>8.1%}"
        for rk in rkeys:
            obj = _sim_result(r, rk)
            if obj is not None:
                s = obj["equity"].reindex(idx)[mask]
                if len(s) >= 2:
                    ret = s.iloc[-1] / s.iloc[0] - 1
                    row += f" {ret:>14.1%} {ret - bah_ret:>+8.1%}"
                else:
                    row += f" {'N/A':>14} {'':>8}"
            else:
                row += f" {'N/A':>14} {'':>8}"
        print(row)


def plot(results: list, strategy: str, fast: int, mid: int, slow: int):
    if not results:
        return

    n      = len(results)
    rkeys  = _res_keys(strategy)
    n_eq   = len(rkeys)
    has_lev = any(rk in ("mom_m", "3t_m") for rk in rkeys)
    rows_per = n_eq + (1 if has_lev else 0)
    hr_unit  = [3] * n_eq + ([1] if has_lev else [])

    colors_map = {
        "mom_m": ["darkorange", "green",     "crimson",  "purple"],
        "3t_m":  ["royalblue",  "teal",      "olive",    "sienna"],
        "mr_m":  ["mediumblue", "darkgreen", "darkred",  "indigo"],
    }

    fig, axes = plt.subplots(
        n * rows_per, 1,
        figsize=(13, sum(hr_unit) * 2.5 * n),
        gridspec_kw={"height_ratios": hr_unit * n},
        squeeze=False,
    )

    for i, r in enumerate(results):
        ticker = r["ticker"]
        bah    = r["bah"]
        cols   = _col_labels(strategy, fast, mid, slow)
        base   = i * rows_per

        for j, rk in enumerate(rkeys):
            ax  = axes[base + j][0]
            obj = _sim_result(r, rk)
            col = colors_map[rk][i % 4]
            m   = r[rk]

            ax.plot(bah.index, bah.values, label="B&H", color="steelblue", linewidth=1.2)
            if obj is not None:
                ax.plot(obj["equity"].index, obj["equity"].values,
                        label=cols[j], color=col, linewidth=1.4)
            ax.set_title(
                f"{ticker} {cols[j]} — CAGR {m['cagr']:.1%}, "
                f"Sharpe {m['sharpe']:.2f}, MaxDD {m['max_dd']:.1%}", fontsize=9)
            ax.set_ylabel("Value ($)")
            ax.legend(fontsize=8); ax.grid(alpha=0.3)
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

        # Leverage panel
        if has_lev:
            ax = axes[base + n_eq][0]
            for rk in ["mom_m", "3t_m"]:
                if rk in rkeys:
                    obj = _sim_result(r, rk)
                    if obj:
                        lev = obj["leverage"]
                        col = colors_map[rk][i % 4]
                        lbl = cols[rkeys.index(rk)]
                        ax.fill_between(lev.index, lev.values, 1, step="post",
                                        alpha=0.4, color=col, label=f"{lbl} leverage")
            ax.axhline(1.0, color="gray", linewidth=0.8, linestyle="--")
            ax.set_ylabel("Leverage")
            ax.set_ylim(-0.1, config.LEVERAGE + 0.3)
            ax.set_yticks([0.0, 1.0, config.LEVERAGE])
            ax.set_yticklabels(["0x\n(cash)", "1x", f"{config.LEVERAGE}x"], fontsize=7)
            ax.legend(fontsize=7, loc="upper left"); ax.grid(alpha=0.3)

    fig.suptitle(f"Stock Backtest — {', '.join(r['ticker'] for r in results)}", fontsize=11)
    plt.tight_layout()

    from datetime import date as _date
    path = f"charts/backtest/stock_backtest_{_date.today()}.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to {path}")
    plt.close()


def _parse_ma(ma_str: str, default_slow: int = MOM_SLOW3) -> tuple[int, int, int]:
    parts = ma_str.split(":")
    return int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else default_slow


if __name__ == "__main__":
    args     = sys.argv[1:]
    strategy = "both"
    fast, mid, slow = 20, 75, MOM_SLOW3

    if "--strategy" in args:
        idx = args.index("--strategy")
        strategy = args[idx + 1]
        args = [a for j, a in enumerate(args) if j != idx and j != idx + 1]

    if "--ma" in args:
        idx = args.index("--ma")
        fast, mid, slow = _parse_ma(args[idx + 1])
        args = [a for j, a in enumerate(args) if j != idx and j != idx + 1]

    tickers = [a.upper() for a in args] if args else ["NVDA", "MSFT", "AAPL"]

    print(f"Backtesting: {', '.join(tickers)}  |  strategy: {strategy}", end="")
    if strategy in ("momentum_3t", "compare"):
        print(f"  |  MA: {fast}/{mid}/{slow}", end="")
    print()

    results = [r for t in tickers
               if (r := backtest(t, strategy, fast, mid, slow)) is not None]
    if results:
        plot(results, strategy, fast, mid, slow)
