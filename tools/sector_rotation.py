"""
Cross-sectional sector rotation: rank the 9 SPDR sector ETFs by trailing
return each month, hold the top N, rebalance monthly.

Every other strategy in this project is single-ticker time-series/absolute
momentum (an MA crossover: is this ticker trending vs its own history).
This is the other classic momentum family -- relative strength across a
universe -- first explored as a one-off backtest 2026-07-03 (see
research/strategy_experiments.md) and promoted here to a first-class,
validated module: walk-forward OOS selection of (lookback, top_n) using the
same discipline as tools.optimize, a permutation significance test (the
cross-sectional analog of tools.significance's circular-shift test -- here
the null is "N random tickers each month" instead of "random timing"), and
an optional leverage overlay that layers this project's usual 2x-when-
confirmed-strong MA mechanism onto each currently-held ticker, to test
whether that turns "comparable CAGR, better Sharpe/drawdown" into genuine
outperformance (research/open_questions.md #8).

Usage:
  python -m tools.sector_rotation                       # backtest at the default params
  python -m tools.sector_rotation --lookback 12 --top-n 3
  python -m tools.sector_rotation --leverage             # + 2x-when-confirmed overlay
  python -m tools.sector_rotation --walk-forward         # OOS param selection, like tools.optimize
  python -m tools.sector_rotation --significance         # permutation test vs random selection
"""

import sys
from collections import defaultdict

import numpy as np
import pandas as pd

from core.data import fetch
from core.metrics import calc
import signals.ma as sig_ma

SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB"]
BENCHMARK = "SPY"

LOOKBACK_GRID_MONTHS = [3, 6, 12]
TOP_N_GRID = [1, 3]
TRADING_DAYS_PER_MONTH = 21
FIRST_TEST_YEAR = 2018

OVERLAY_MA_FAST = 10
OVERLAY_MA_SLOW = 100
OVERLAY_LEVERAGE = 2.0


def _fetch_universe(tickers=SECTOR_ETFS):
    prices = {t: fetch(t) for t in tickers}
    df = pd.concat(prices, axis=1).dropna()
    return df


def _rebalance_dates(index: pd.DatetimeIndex, warmup_days: int):
    """Last trading day of each month, skipping the warmup period."""
    s = pd.Series(index, index=index)
    month_ends = s.groupby([index.year, index.month]).max()
    return [d for d in month_ends if index.get_loc(d) >= warmup_days]


def rank_top_n(df: pd.DataFrame, as_of: pd.Timestamp, lookback_days: int, top_n: int):
    """Return the top_n column names by trailing return as of `as_of`."""
    loc = df.index.get_loc(as_of)
    start_loc = loc - lookback_days
    if start_loc < 0:
        return None
    trailing_ret = df.iloc[loc] / df.iloc[start_loc] - 1
    return list(trailing_ret.sort_values(ascending=False).index[:top_n])


def build_equity_curve(df: pd.DataFrame, lookback_days: int, top_n: int,
                       capital: float = 100_000, use_leverage: bool = False,
                       ma_fast: int = OVERLAY_MA_FAST, ma_slow: int = OVERLAY_MA_SLOW,
                       leverage: float = OVERLAY_LEVERAGE):
    """
    Rank-and-hold, rebalanced at each month-end, held from the following
    trading day through the next month-end. Returns a daily equity Series
    spanning the whole df (empty/NaN-free from the first valid rebalance
    onward) so it plugs directly into core.metrics.calc without any
    frequency-reindexing footgun.

    use_leverage: instead of a flat 1x buy-and-hold on each held ticker
    within the month, scale that ticker's daily return by `leverage` on days
    its own MA(ma_fast/ma_slow) signal is bullish, 1x otherwise -- the
    "2x-when-confirmed-strong" mechanism used everywhere else in this
    project, layered onto the cross-sectional selection instead of replacing it.
    """
    warmup = lookback_days + 5
    dates = _rebalance_dates(df.index, warmup)
    if len(dates) < 2:
        return pd.Series(dtype=float)

    if use_leverage:
        signals = {t: sig_ma.signal(df[t], ma_fast, ma_slow) for t in df.columns}

    equity_chunks = []
    current_capital = capital

    for i in range(len(dates) - 1):
        reb_date = dates[i]
        next_reb = dates[i + 1]
        holding = df.index[(df.index > reb_date) & (df.index <= next_reb)]
        if len(holding) == 0:
            continue
        # include the entry (rebalance) date so the first holding day's return
        # is measured against the actual entry price, not silently dropped
        with_entry = df.index[(df.index >= reb_date) & (df.index <= next_reb)]

        picks = rank_top_n(df, reb_date, lookback_days, top_n)
        if not picks:
            continue

        per_ticker_capital = current_capital / len(picks)
        period_equity = pd.Series(0.0, index=holding)

        for t in picks:
            rets = df[t].reindex(with_entry).pct_change().fillna(0.0)
            if use_leverage:
                sig = signals[t].reindex(with_entry, method="ffill").fillna(0)
                rets = rets * sig.map({1: leverage, 0: 1.0})
            growth = (1 + rets).cumprod().reindex(holding)
            period_equity += per_ticker_capital * growth

        equity_chunks.append(period_equity)
        current_capital = float(period_equity.iloc[-1])

    if not equity_chunks:
        return pd.Series(dtype=float)
    return pd.concat(equity_chunks)


def run(lookback_months: int = 12, top_n: int = 3, use_leverage: bool = False,
       capital: float = 100_000):
    df = _fetch_universe()
    lookback_days = lookback_months * TRADING_DAYS_PER_MONTH
    equity = build_equity_curve(df, lookback_days, top_n, capital, use_leverage)
    if equity.empty:
        return None
    metrics = calc(equity)
    return {"equity": equity, "metrics": metrics,
           "lookback_months": lookback_months, "top_n": top_n,
           "use_leverage": use_leverage}


# ---------------------------------------------------------------------------
# Walk-forward OOS param selection (same discipline as tools.optimize)
# ---------------------------------------------------------------------------

def walk_forward(first_test_year: int = FIRST_TEST_YEAR, use_leverage: bool = False):
    """
    For each OOS year, pick the (lookback, top_n) combo with the best Sharpe
    on data through the prior year-end, then evaluate it OOS on that year.
    No param is ever selected using data from the year it's tested on.
    """
    df = _fetch_universe()
    spy_prices = fetch(BENCHMARK)
    current_year = pd.Timestamp.now().year

    fold_records = []
    appearances = defaultdict(int)

    for test_year in range(first_test_year, current_year + 1):
        train = df[df.index <= f"{test_year - 1}-12-31"]
        oos = df[(df.index >= f"{test_year}-01-01") & (df.index <= f"{test_year}-12-31")]
        if len(oos) < 20:
            continue

        best = None
        for lb in LOOKBACK_GRID_MONTHS:
            for tn in TOP_N_GRID:
                eq = build_equity_curve(train, lb * TRADING_DAYS_PER_MONTH, tn,
                                        use_leverage=use_leverage)
                if eq.empty or len(eq) < 40:
                    continue
                m = calc(eq)
                if best is None or m["sharpe"] > best["sharpe"]:
                    best = {"lookback": lb, "top_n": tn, "sharpe": m["sharpe"]}

        if best is None:
            fold_records.append({"test_year": test_year, "skipped": True})
            continue

        appearances[(best["lookback"], best["top_n"])] += 1

        oos_full = df[df.index <= f"{test_year}-12-31"]
        eq_oos = build_equity_curve(oos_full, best["lookback"] * TRADING_DAYS_PER_MONTH,
                                    best["top_n"], use_leverage=use_leverage)
        eq_oos_year = eq_oos[eq_oos.index.year == test_year]
        if eq_oos_year.empty or len(eq_oos_year) < 20:
            fold_records.append({"test_year": test_year, "skipped": True})
            continue

        m = calc(eq_oos_year)
        spy_year = spy_prices[spy_prices.index.year == test_year]
        bah_cagr = calc(spy_year)["cagr"] if len(spy_year) >= 20 else None

        fold_records.append({
            "test_year": test_year, "skipped": False,
            "lookback": best["lookback"], "top_n": best["top_n"],
            "oos_cagr": m["cagr"], "oos_sharpe": m["sharpe"], "oos_max_dd": m["max_dd"],
            "bah_cagr": bah_cagr,
        })

    return fold_records, appearances


# ---------------------------------------------------------------------------
# Significance test: real ranking vs random N-ticker selection each month
# ---------------------------------------------------------------------------

def significance_test(lookback_months: int = 12, top_n: int = 3,
                      n_shifts: int = 1000, seed: int = 0, use_leverage: bool = False,
                      ma_fast: int = OVERLAY_MA_FAST, ma_slow: int = OVERLAY_MA_SLOW,
                      leverage: float = OVERLAY_LEVERAGE):
    """
    Cross-sectional analog of tools.significance's circular-shift test. The
    real strategy picks the top_n tickers by trailing return each month;
    the null here instead picks top_n *random* tickers each month (same
    universe size, same rebalance calendar, same holding-period length,
    and -- critically -- the same per-ticker leverage overlay if enabled) --
    it asks whether the specific ranking rule beats random selection of the
    same exposure, not whether being long sector ETFs (or leveraging them) at
    all is a good idea. Applying the leverage overlay only to the actual
    strategy and not the null would conflate "this ranking rule has skill"
    with "2x leverage in a rising market raises CAGR," which this project's
    own methodology finding (research/methodology.md) already established
    has nothing to do with timing skill -- so both sides of the comparison
    must use identical per-ticker mechanics.
    """
    df = _fetch_universe()
    lookback_days = lookback_months * TRADING_DAYS_PER_MONTH
    actual_eq = build_equity_curve(df, lookback_days, top_n, use_leverage=use_leverage,
                                   ma_fast=ma_fast, ma_slow=ma_slow, leverage=leverage)
    if actual_eq.empty:
        return None
    actual = calc(actual_eq)

    rng = np.random.default_rng(seed)
    warmup = lookback_days + 5
    dates = _rebalance_dates(df.index, warmup)
    n_tickers = len(df.columns)

    if use_leverage:
        signals = {t: sig_ma.signal(df[t], ma_fast, ma_slow) for t in df.columns}

    # Precompute each window's per-ticker growth-factor path once (outside the
    # shift loop) -- growth doesn't depend on which tickers get picked, only
    # the random *choice* of columns does, so this is the expensive part that
    # doesn't need to be redone 1000 times. Must match build_equity_curve's
    # per-ticker leverage mechanics exactly so the null is a fair comparison.
    windows = []   # list of (n_tickers, window_len) growth-factor arrays
    for i in range(len(dates) - 1):
        reb_date, next_reb = dates[i], dates[i + 1]
        holding = df.index[(df.index > reb_date) & (df.index <= next_reb)]
        if len(holding) == 0:
            continue
        with_entry = df.index[(df.index >= reb_date) & (df.index <= next_reb)]
        rets = df.reindex(with_entry).pct_change().fillna(0.0)
        if use_leverage:
            for t in df.columns:
                sig = signals[t].reindex(with_entry, method="ffill").fillna(0)
                rets[t] = rets[t] * sig.map({1: leverage, 0: 1.0})
        growth = (1 + rets).cumprod().reindex(holding).to_numpy().T   # (n_tickers, window_len)
        windows.append(growth)

    random_cagrs, random_sharpes = [], []
    for _ in range(n_shifts):
        current_capital = 100_000.0
        path_chunks = []
        for growth in windows:
            picks_idx = rng.choice(n_tickers, size=top_n, replace=False)
            period_growth = growth[picks_idx, :].mean(axis=0)
            period_equity = current_capital * period_growth
            path_chunks.append(period_equity)
            current_capital = float(period_equity[-1])
        if not path_chunks:
            continue
        path = np.concatenate(path_chunks)
        n_years = len(path) / 252
        total = path[-1] / 100_000 - 1
        cagr = (1 + total) ** (1 / n_years) - 1 if n_years > 0 else 0.0
        daily_ret = np.diff(path) / path[:-1]
        sharpe = (daily_ret.mean() / daily_ret.std() * (252 ** 0.5)
                 if daily_ret.std() > 0 else 0.0)
        random_cagrs.append(cagr)
        random_sharpes.append(sharpe)

    random_cagrs = np.array(random_cagrs)
    random_sharpes = np.array(random_sharpes)
    p_cagr = float((random_cagrs >= actual["cagr"]).mean())
    p_sharpe = float((random_sharpes >= actual["sharpe"]).mean())

    return {
        "actual_cagr": actual["cagr"], "actual_sharpe": actual["sharpe"],
        "random_cagrs": random_cagrs, "random_sharpes": random_sharpes,
        "p_cagr": p_cagr, "p_sharpe": p_sharpe,
    }


def _verdict(p):
    if p < 0.05:
        return "SIGNIFICANT"
    if p < 0.10:
        return "borderline"
    return "NOT significant — indistinguishable from random selection of the same universe size"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def analyze(lookback_months=12, top_n=3, use_leverage=False,
           show_walk_forward=False, show_significance=False):
    r = run(lookback_months, top_n, use_leverage)
    if r is None:
        print("Not enough data to backtest sector rotation.")
        return
    m = r["metrics"]
    lev_label = " + 2x-when-confirmed leverage overlay" if use_leverage else ""
    print(f"\n{'='*70}")
    print(f"  Sector rotation — {lookback_months}mo lookback, top-{top_n}{lev_label}")
    print(f"{'='*70}")
    print(f"  CAGR: {m['cagr']:.1%}   Sharpe: {m['sharpe']:.2f}   MaxDD: {m['max_dd']:.1%}")

    spy = fetch(BENCHMARK)
    spy_eq = spy.reindex(r["equity"].index, method="ffill") / spy.reindex(r["equity"].index, method="ffill").iloc[0] * 100_000
    spy_m = calc(spy_eq)
    print(f"  SPY B&H over same period: CAGR {spy_m['cagr']:.1%}   "
          f"Sharpe {spy_m['sharpe']:.2f}   MaxDD {spy_m['max_dd']:.1%}")

    if show_walk_forward:
        print(f"\n  Walk-forward OOS param selection (best Sharpe on prior data):")
        fold_records, appearances = walk_forward(use_leverage=use_leverage)
        print(f"  {'Year':<6} {'Params':<14} {'OOS CAGR':>9} {'OOS Sharpe':>11} "
              f"{'OOS MaxDD':>10} {'vs SPY':>8}")
        for f in fold_records:
            if f.get("skipped"):
                print(f"  {f['test_year']:<6} SKIPPED — no combo produced enough OOS data")
                continue
            vs = f["oos_cagr"] - f["bah_cagr"] if f["bah_cagr"] is not None else float("nan")
            print(f"  {f['test_year']:<6} {str(f['lookback'])+'mo/top'+str(f['top_n']):<14} "
                  f"{f['oos_cagr']:>9.1%} {f['oos_sharpe']:>11.2f} {f['oos_max_dd']:>10.1%} "
                  f"{vs:>+7.1%}")
        print(f"\n  Param consistency (appearances across folds):")
        for (lb, tn), count in sorted(appearances.items(), key=lambda x: -x[1]):
            print(f"    {lb}mo lookback, top-{tn}: {count} folds")

    if show_significance:
        print(f"\n  Significance test ({lookback_months}mo/top-{top_n}, 1000 random-selection shifts):")
        sig = significance_test(lookback_months, top_n, use_leverage=use_leverage)
        if sig is None:
            print("    Not enough data.")
        else:
            print(f"    Actual CAGR {sig['actual_cagr']:.1%} vs random-selection median "
                  f"{np.median(sig['random_cagrs']):.1%}   p={sig['p_cagr']:.3f}   "
                  f"{_verdict(sig['p_cagr'])}")
            print(f"    Actual Sharpe {sig['actual_sharpe']:.2f} vs random-selection median "
                  f"{np.median(sig['random_sharpes']):.2f}   p={sig['p_sharpe']:.3f}   "
                  f"{_verdict(sig['p_sharpe'])}")


if __name__ == "__main__":
    args = sys.argv[1:]
    lookback = 12
    top_n = 3
    use_leverage = "--leverage" in args
    show_wf = "--walk-forward" in args
    show_sig = "--significance" in args
    args = [a for a in args if a not in ("--leverage", "--walk-forward", "--significance")]

    if "--lookback" in args:
        idx = args.index("--lookback")
        lookback = int(args[idx + 1])
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]
    if "--top-n" in args:
        idx = args.index("--top-n")
        top_n = int(args[idx + 1])
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    analyze(lookback_months=lookback, top_n=top_n, use_leverage=use_leverage,
           show_walk_forward=show_wf, show_significance=show_sig)
