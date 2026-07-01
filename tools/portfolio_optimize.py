"""
Portfolio-level walk-forward optimizer.

Sweeps MA param combinations across all portfolio tickers jointly,
evaluating the combined portfolio result (Sharpe, CAGR, MaxDD, fees)
rather than optimizing each ticker in isolation.

This catches problems that per-ticker optimization misses — e.g. a fast
MA that looks good per-ticker but generates excess fees at portfolio level.

Usage:
  python -m tools.portfolio_optimize                   # default portfolio
  python -m tools.portfolio_optimize SPMO:0.8 GLD:0.2  # custom weights
"""

import sys
import itertools
from collections import defaultdict
import pandas as pd

from core import config
from core.data import fetch
from core.metrics import calc
from core.simulator import run as simulate
from signals import ma as sig_ma
from strategies import momentum
from tools.portfolio import DEFAULT_PORTFOLIO

MA_FAST_WINDOWS = [10, 20, 30, 50]
MA_SLOW_WINDOWS = [50, 100, 150, 200]
FIRST_TEST_YEAR = 2018
TOP_N           = 5
MIN_AVG_ALPHA   = 0.05   # portfolio must beat B&H CAGR by at least 5% avg across folds


def _ma_combos():
    return [(f, s) for f, s in itertools.product(MA_FAST_WINDOWS, MA_SLOW_WINDOWS) if f < s]


def _simulate_all(prices_dict, weights):
    """
    Pre-simulate every (ticker, fast, slow) combination on full price history.
    Returns: sims[ticker][(fast, slow)] = equity Series
    """
    combos = _ma_combos()
    sims   = {}
    for ticker, prices in prices_dict.items():
        sims[ticker] = {}
        for fast, slow in combos:
            sig    = sig_ma.signal(prices, fast, slow)
            pos    = momentum.positions(sig)
            result = simulate(prices, pos, capital=config.INITIAL_CAPITAL * weights[ticker])
            sims[ticker][(fast, slow)] = result["equity"]
    return sims


def _bah_equity(prices_dict, weights, idx):
    total = None
    for ticker, prices in prices_dict.items():
        p    = prices.reindex(idx).dropna()
        cap  = config.INITIAL_CAPITAL * weights[ticker]
        leg  = cap * (p / p.iloc[0])
        total = leg if total is None else total + leg.reindex(total.index)
    return total


def _combine(sims, tickers, joint_combo, idx):
    """Combine leg equity curves for a joint param combo on a given index slice."""
    total = None
    for ticker, (fast, slow) in zip(tickers, joint_combo):
        leg = sims[ticker][(fast, slow)].reindex(idx).dropna()
        if len(leg) < 2:
            return None
        total = leg if total is None else (total + leg).reindex(
            total.index.intersection(leg.index))
    return total


def _build_folds(common_idx):
    current_year = pd.Timestamp.now().year
    folds = []
    for test_year in range(FIRST_TEST_YEAR, current_year):
        train = common_idx[common_idx.year < test_year]
        oos   = common_idx[common_idx.year == test_year]
        if len(train) < 200 or len(oos) < 20:
            continue
        folds.append((train, oos, test_year))
    return folds


def _combo_label(tickers, joint_combo):
    return "  ".join(f"{t}:MA{f}/{s}" for t, (f, s) in zip(tickers, joint_combo))


def optimize(portfolio: dict) -> list | None:
    tickers = list(portfolio.keys())
    weights = {t: portfolio[t]["weight"] for t in tickers}
    current_combo = tuple(
        (portfolio[t]["ma_fast"], portfolio[t]["ma_slow"]) for t in tickers
    )

    print(f"Fetching prices...")
    prices_dict = {t: fetch(t) for t in tickers}

    print(f"Pre-simulating {len(tickers)} tickers × {len(_ma_combos())} param combos...")
    sims = _simulate_all(prices_dict, weights)

    # Common index across all tickers
    common_idx = list(prices_dict.values())[0].index
    for p in prices_dict.values():
        common_idx = common_idx.intersection(p.index)

    folds        = _build_folds(common_idx)
    joint_combos = list(itertools.product(_ma_combos(), repeat=len(tickers)))

    current_year = pd.Timestamp.now().year
    print(f"\nPortfolio-level walk-forward optimization")
    print(f"Tickers       : {', '.join(tickers)}")
    print(f"Joint combos  : {len(joint_combos)}")
    print(f"OOS folds     : {FIRST_TEST_YEAR}–{current_year - 1}")
    print(f"Constraints   : max_dd > {config.MAX_DRAWDOWN_LIMIT:.0%}, margin calls = 0")

    appearances = defaultdict(int)
    oos_records = []

    for train_idx, oos_idx, test_year in folds:
        fold_label = f"{test_year} OOS  (train: {config.START[:4]}–{test_year-1})"

        bah_train      = _bah_equity(prices_dict, weights, train_idx)
        bah_train_m    = calc(bah_train) if bah_train is not None and len(bah_train) >= 2 else None
        bah_train_cagr = bah_train_m["cagr"] if bah_train_m else 0.0

        # Score all joint combos on training data
        train_scores = []
        for jc in joint_combos:
            eq = _combine(sims, tickers, jc, train_idx)
            if eq is None or len(eq) < 20:
                continue
            m = calc(eq)
            if m["max_dd"] < config.MAX_DRAWDOWN_LIMIT:
                continue
            alpha = m["cagr"] - bah_train_cagr
            train_scores.append({"combo": jc, "sharpe": m["sharpe"], "cagr": m["cagr"],
                                 "alpha": alpha})

        if not train_scores:
            continue

        # Rank by alpha vs B&H — avoids rewarding near-constant-bullish strategies
        top = sorted(train_scores, key=lambda x: x["alpha"], reverse=True)[:TOP_N]

        bah = _bah_equity(prices_dict, weights, oos_idx)
        bah_m = calc(bah) if bah is not None and len(bah) >= 2 else None

        for entry in top:
            jc  = entry["combo"]
            appearances[jc] += 1
            eq  = _combine(sims, tickers, jc, oos_idx)
            if eq is None or len(eq) < 2:
                continue
            m = calc(eq)
            oos_records.append({
                "fold":       fold_label,
                "combo":      jc,
                "oos_cagr":   m["cagr"],
                "oos_sharpe": m["sharpe"],
                "oos_max_dd": m["max_dd"],
                "bah_cagr":   bah_m["cagr"] if bah_m else float("nan"),
            })

    if not oos_records:
        print("No results passed constraints.")
        return None

    oos_df = pd.DataFrame(oos_records)
    return _print_results(oos_df, appearances, tickers, folds, current_combo)


def _print_results(oos_df, appearances, tickers, folds, current_combo):
    n_folds = len(folds)

    def _avg_sharpe(combo):
        sub = oos_df[oos_df["combo"].apply(lambda c: c == combo)]
        return sub["oos_sharpe"].mean() if not sub.empty else -999

    def _avg_alpha(combo):
        sub = oos_df[oos_df["combo"].apply(lambda c: c == combo)]
        return (sub["oos_cagr"] - sub["bah_cagr"]).mean() if not sub.empty else -999

    ranked_all = sorted(appearances.items(),
                        key=lambda x: (x[1], _avg_sharpe(x[0])), reverse=True)
    ranked     = [(c, n) for c, n in ranked_all if _avg_alpha(c) >= MIN_AVG_ALPHA]
    excluded   = [(c, n) for c, n in ranked_all if _avg_alpha(c) < MIN_AVG_ALPHA]

    if not ranked:
        print("  No combos met the MIN_AVG_ALPHA threshold — showing all:")
        ranked = ranked_all

    w = max((len(_combo_label(tickers, c)) for c, _ in (ranked + excluded)[:TOP_N]),
            default=30) + 2

    print(f"\n{'='*max(w+50, 78)}")
    print(f"  Consistency (top {TOP_N} by portfolio alpha vs B&H across {n_folds} folds):")
    print(f"{'='*max(w+50, 78)}")
    print(f"  {'Config':<{w}} {'Count':>6} {'Avg CAGR':>10} "
          f"{'Avg Sharpe':>11} {'Avg MaxDD':>10} {'Avg vs B&H':>12}")
    print(f"  {'-'*w} {'-'*6} {'-'*10} {'-'*11} {'-'*10} {'-'*12}")

    for combo, count in ranked[:TOP_N]:
        sub    = oos_df[oos_df["combo"].apply(lambda c: c == combo)]
        label  = _combo_label(tickers, combo)
        vs_bah = (sub["oos_cagr"] - sub["bah_cagr"]).mean()
        print(f"  {label:<{w}} {count:>6}  "
              f"{sub['oos_cagr'].mean():>9.1%}  "
              f"{sub['oos_sharpe'].mean():>10.2f}  "
              f"{sub['oos_max_dd'].mean():>9.1%}  "
              f"{vs_bah:>+11.1%}")

    if excluded:
        excl_labels = ", ".join(_combo_label(tickers, c) for c, _ in excluded[:2])
        print(f"\n  (excluded — avg alpha < {MIN_AVG_ALPHA:.0%}: {excl_labels}"
              + (f" + {len(excluded)-2} more" if len(excluded) > 2 else "") + ")")

    # Current config in results?
    curr_count = appearances.get(current_combo, 0)
    curr_sub   = oos_df[oos_df["combo"].apply(lambda c: c == current_combo)]
    curr_sharpe = curr_sub["oos_sharpe"].mean() if not curr_sub.empty else float("nan")

    best_combo, best_count = ranked[0]
    print(f"\n  Recommended : {_combo_label(tickers, best_combo)}  "
          f"({best_count}/{n_folds} folds, avg Sharpe {_avg_sharpe(best_combo):.2f})")
    print(f"  Current     : {_combo_label(tickers, current_combo)}  "
          f"({'not in top 5 any fold' if curr_count == 0 else f'{curr_count}/{n_folds} folds'}"
          + (f", avg Sharpe {curr_sharpe:.2f}" if curr_count > 0 else "") + ")")

    return ranked, tickers


def _parse_args(args):
    portfolio = {}
    for arg in args:
        parts = arg.split(":")
        ticker, weight = parts[0].upper(), float(parts[1])
        # Use DEFAULT_PORTFOLIO params as starting point if available
        base = DEFAULT_PORTFOLIO.get(ticker, {"ma_fast": 50, "ma_slow": 100})
        portfolio[ticker] = {**base, "weight": weight}
    total = sum(v["weight"] for v in portfolio.values())
    if abs(total - 1.0) > 0.01:
        print(f"Weights sum to {total:.2%}, expected 100%.")
        sys.exit(1)
    return portfolio


if __name__ == "__main__":
    args      = sys.argv[1:]
    portfolio = _parse_args(args) if args else DEFAULT_PORTFOLIO
    optimize(portfolio)
