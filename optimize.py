"""
Parameter sweep + rolling walk-forward validation for the momentum margin strategy.

Rolling walk-forward approach:
  - Expand training window year by year (anchored start at TRAIN_START)
  - Test on the following calendar year (OOS window = 1 year each)
  - Final fold tests on the most recent partial year
  - Selects params that appear most consistently in top N across all folds

Usage:
  python optimize.py          # default tickers
  python optimize.py SPMO QQQ
"""

import sys
import itertools
from collections import defaultdict
import yfinance as yf
import pandas as pd

# --- Config ---
DEFAULT_TICKERS   = ["SPMO", "QQQ"]
TRAIN_START       = "2020-01-01"   # anchored start for all training windows
FIRST_TEST_YEAR   = 2022           # first OOS year (train on everything before this)
LEVERAGE          = 2.0
MARGIN_RATE       = 0.048
INITIAL_CAPITAL   = 10_000
MAINTENANCE_MARGIN = 0.30

FEE_PER_SHARE     = 0.0049 + 0.005
FEE_MIN_PER_ORDER = 0.99 + 1.00

MAX_DRAWDOWN_LIMIT = -0.50
MAX_MARGIN_CALLS   = 0
TOP_N              = 5

FAST_WINDOWS = [10, 20, 30, 50]
SLOW_WINDOWS = [50, 100, 150, 200]


def calc_trade_fee(shares):
    return max(shares * FEE_PER_SHARE, FEE_MIN_PER_ORDER)


def simulate(prices, ma_fast, ma_slow):
    """Run strategy simulation on a price series. Returns metrics dict."""
    df = pd.DataFrame({"price": prices})
    df["ma_fast"] = df["price"].rolling(ma_fast).mean()
    df["ma_slow"] = df["price"].rolling(ma_slow).mean()
    df.dropna(inplace=True)
    df["signal"] = (df["ma_fast"] > df["ma_slow"]).astype(int)

    if len(df) < 2:
        return None

    daily_borrow_rate = MARGIN_RATE / 252
    equity = INITIAL_CAPITAL
    current_leverage = 1.0
    margin_calls = 0
    total_fees = 0.0
    equity_curve = []
    prev_price = None

    for _, row in df.iterrows():
        price = row["price"]
        signal = row["signal"]

        if prev_price is not None:
            daily_ret = (price - prev_price) / prev_price
            borrowed_fraction = current_leverage - 1.0
            equity *= 1 + current_leverage * daily_ret - borrowed_fraction * daily_borrow_rate

        target_leverage = LEVERAGE if signal == 1 else 1.0

        if target_leverage != current_leverage and price > 0:
            shares_traded = abs(equity * target_leverage - equity * current_leverage) / price
            equity -= calc_trade_fee(shares_traded)
            total_fees += calc_trade_fee(shares_traded)

        position_value = equity * target_leverage
        equity_ratio = equity / position_value if position_value > 0 else 1.0

        if equity_ratio < MAINTENANCE_MARGIN and equity > 0:
            forced_leverage = max(1.0, min(target_leverage, 1.0 / MAINTENANCE_MARGIN))
            shares_liq = abs(equity * target_leverage - equity * forced_leverage) / price
            equity -= calc_trade_fee(shares_liq)
            total_fees += calc_trade_fee(shares_liq)
            current_leverage = forced_leverage
            margin_calls += 1
        else:
            current_leverage = target_leverage

        equity_curve.append(equity)
        prev_price = price

    s = pd.Series(equity_curve, index=df.index)
    ret = s.pct_change().dropna()
    n_years = len(ret) / 252
    if n_years < 0.1:
        return None
    total = s.iloc[-1] / s.iloc[0] - 1
    cagr = (1 + total) ** (1 / n_years) - 1
    sharpe = ret.mean() / ret.std() * (252 ** 0.5) if ret.std() > 0 else 0
    max_dd = (s / s.cummax() - 1).min()

    return {"cagr": cagr, "sharpe": sharpe, "max_dd": max_dd,
            "margin_calls": margin_calls, "total_fees": total_fees}


def bah_metrics(prices):
    ret = prices.pct_change().dropna()
    n_years = len(ret) / 252
    total = prices.iloc[-1] / prices.iloc[0] - 1
    cagr = (1 + total) ** (1 / n_years) - 1 if n_years > 0 else 0
    sharpe = ret.mean() / ret.std() * (252 ** 0.5) if ret.std() > 0 else 0
    max_dd = (prices / prices.cummax() - 1).min()
    return {"cagr": cagr, "sharpe": sharpe, "max_dd": max_dd}


def build_folds(prices, first_test_year):
    """
    Returns list of (train_prices, oos_prices, fold_label) tuples.
    Training window is anchored at TRAIN_START and expands each year.
    OOS window is one calendar year at a time.
    """
    folds = []
    current_year = pd.Timestamp.now().year
    test_years = range(first_test_year, current_year + 1)

    for test_year in test_years:
        train_end = f"{test_year - 1}-12-31"
        oos_start = f"{test_year}-01-01"
        oos_end   = f"{test_year}-12-31"

        train = prices[prices.index <= train_end]
        oos   = prices[(prices.index >= oos_start) & (prices.index <= oos_end)]

        if len(train) < max(SLOW_WINDOWS) + 10 or len(oos) < 20:
            continue

        label = f"{test_year} OOS  (train: {TRAIN_START[:4]}–{test_year-1})"
        folds.append((train, oos, label))

    return folds


def sweep_fold(train_prices, combos):
    """Run all combos on training prices, return DataFrame of results."""
    results = []
    for fast, slow in combos:
        if len(train_prices) < slow + 10:
            continue
        m = simulate(train_prices, fast, slow)
        if m is None:
            continue
        m["fast"] = fast
        m["slow"] = slow
        results.append(m)
    return pd.DataFrame(results)


def run(tickers):
    import datetime
    current_year = pd.Timestamp.now().year
    combos = [(f, s) for f, s in itertools.product(FAST_WINDOWS, SLOW_WINDOWS) if f < s]

    print(f"\nRolling walk-forward validation")
    print(f"Train start : {TRAIN_START}  (expanding window)")
    print(f"OOS folds   : {FIRST_TEST_YEAR}–{current_year}  (1 year each)")
    print(f"Tickers     : {', '.join(tickers)}")

    for ticker in tickers:
        raw = yf.download(ticker, start=TRAIN_START, auto_adjust=True, progress=False)
        prices_all = raw["Close"].squeeze().dropna()

        folds = build_folds(prices_all, FIRST_TEST_YEAR)
        if not folds:
            print(f"\n{ticker}: not enough data for walk-forward.")
            continue

        print(f"\n{'='*65}")
        print(f"  {ticker}")
        print(f"{'='*65}")

        # Track how many times each combo appears in top N across folds
        appearances = defaultdict(int)
        oos_records = []  # (fold_label, fast, slow, oos_metrics, bah_metrics)

        for train, oos, fold_label in folds:
            df_results = sweep_fold(train, combos)
            if df_results.empty:
                continue

            passing = df_results[
                (df_results["max_dd"] >= MAX_DRAWDOWN_LIMIT) &
                (df_results["margin_calls"] <= MAX_MARGIN_CALLS)
            ].sort_values("cagr", ascending=False).head(TOP_N)

            for _, row in passing.iterrows():
                key = (int(row.fast), int(row.slow))
                appearances[key] += 1

            # Validate top params on OOS
            bah = bah_metrics(oos)
            for _, row in passing.iterrows():
                fast, slow = int(row.fast), int(row.slow)
                m = simulate(oos, fast, slow)
                if m:
                    oos_records.append({
                        "fold": fold_label, "fast": fast, "slow": slow,
                        **{f"oos_{k}": v for k, v in m.items()},
                        "bah_cagr": bah["cagr"], "bah_max_dd": bah["max_dd"]
                    })

        # --- Per-fold OOS results ---
        print(f"\n  Per-fold OOS results:")
        print(f"  {'Fold':<32} {'MA':>8} {'CAGR':>8} {'MaxDD':>8} {'vs B&H':>8} {'Pass?':>6}")
        print(f"  {'-'*32} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*6}")

        oos_df = pd.DataFrame(oos_records)
        if not oos_df.empty:
            for _, r in oos_df.iterrows():
                passes = (r["oos_max_dd"] >= MAX_DRAWDOWN_LIMIT and
                          r["oos_margin_calls"] <= MAX_MARGIN_CALLS)
                diff = r["oos_cagr"] - r["bah_cagr"]
                print(f"  {r['fold']:<32} {int(r.fast)}/{int(r.slow):>4}  "
                      f"{r['oos_cagr']:>7.1%}  {r['oos_max_dd']:>7.1%}  "
                      f"{diff:>+7.1%}  {'YES' if passes else 'NO':>6}")

        # --- Consistency ranking ---
        print(f"\n  Consistency ranking (appearances in top {TOP_N} across {len(folds)} folds):")
        print(f"  {'MA':>8} {'Appearances':>12} {'Avg OOS CAGR':>14} {'Avg OOS MaxDD':>14} {'Avg vs B&H':>12}")
        print(f"  {'-'*8} {'-'*12} {'-'*14} {'-'*14} {'-'*12}")

        ranked = sorted(appearances.items(), key=lambda x: x[1], reverse=True)
        for (fast, slow), count in ranked[:TOP_N]:
            subset = oos_df[(oos_df.fast == fast) & (oos_df.slow == slow)]
            if subset.empty:
                continue
            avg_cagr  = subset["oos_cagr"].mean()
            avg_dd    = subset["oos_max_dd"].mean()
            avg_vs_bah = (subset["oos_cagr"] - subset["bah_cagr"]).mean()
            print(f"  {fast}/{slow:>4}  {count:>12}  {avg_cagr:>13.1%}  "
                  f"{avg_dd:>13.1%}  {avg_vs_bah:>+11.1%}")

        # --- Recommendation ---
        if ranked:
            best = ranked[0][0]
            print(f"\n  Recommended: MA {best[0]}/{best[1]}  "
                  f"(most consistent across all folds)")


if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_TICKERS
    run(tickers)
