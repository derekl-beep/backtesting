"""
Parameter sweep + walk-forward validation for the momentum margin strategy.

In-sample  (optimize): 2020-01-01 to 2022-12-31
Out-of-sample (validate): 2023-01-01 to present

Sweeps MA fast/slow window combinations, filters by hard constraints,
then validates surviving params on unseen data.

Usage:
  python optimize.py          # runs on default tickers
  python optimize.py SPMO QQQ
"""

import sys
import itertools
import yfinance as yf
import pandas as pd

# --- Config ---
DEFAULT_TICKERS  = ["SPMO", "QQQ"]
IN_SAMPLE_START  = "2020-01-01"
IN_SAMPLE_END    = "2022-12-31"
OOS_START        = "2023-01-01"

LEVERAGE          = 2.0
MARGIN_RATE       = 0.048
INITIAL_CAPITAL   = 10_000
MAINTENANCE_MARGIN = 0.30

FEE_PER_SHARE     = 0.0049 + 0.005
FEE_MIN_PER_ORDER = 0.99 + 1.00

# Hard constraints
MAX_DRAWDOWN_LIMIT = -0.50   # max drawdown must be better than this
MAX_MARGIN_CALLS   = 0       # zero margin calls allowed

# Parameter grid
FAST_WINDOWS = [10, 20, 30, 50]
SLOW_WINDOWS = [50, 100, 150, 200]
TOP_N        = 5             # how many in-sample winners to validate out-of-sample


def calc_trade_fee(shares):
    return max(shares * FEE_PER_SHARE, FEE_MIN_PER_ORDER)


def simulate(prices, ma_fast, ma_slow):
    df = pd.DataFrame({"price": prices})
    df["ma_fast"] = df["price"].rolling(ma_fast).mean()
    df["ma_slow"] = df["price"].rolling(ma_slow).mean()
    df.dropna(inplace=True)
    df["signal"] = (df["ma_fast"] > df["ma_slow"]).astype(int)

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
            fee = calc_trade_fee(shares_traded)
            equity -= fee
            total_fees += fee

        position_value = equity * target_leverage
        equity_ratio = equity / position_value if position_value > 0 else 1.0

        if equity_ratio < MAINTENANCE_MARGIN and equity > 0:
            forced_leverage = min(target_leverage, 1.0 / MAINTENANCE_MARGIN)
            new_leverage = max(1.0, forced_leverage)
            shares_liquidated = abs(equity * target_leverage - equity * new_leverage) / price
            fee = calc_trade_fee(shares_liquidated)
            equity -= fee
            total_fees += fee
            current_leverage = new_leverage
            margin_calls += 1
        else:
            current_leverage = target_leverage

        equity_curve.append(equity)
        prev_price = price

    s = pd.Series(equity_curve, index=df.index)
    ret = s.pct_change().dropna()
    n_years = len(ret) / 252
    total = s.iloc[-1] / s.iloc[0] - 1
    cagr = (1 + total) ** (1 / n_years) - 1 if n_years > 0 else 0
    sharpe = ret.mean() / ret.std() * (252 ** 0.5) if ret.std() > 0 else 0
    max_dd = (s / s.cummax() - 1).min()

    return {"cagr": cagr, "sharpe": sharpe, "max_dd": max_dd,
            "margin_calls": margin_calls, "total_fees": total_fees}


def bah_metrics(prices):
    ret = prices.pct_change().dropna()
    n_years = len(ret) / 252
    total = prices.iloc[-1] / prices.iloc[0] - 1
    cagr = (1 + total) ** (1 / n_years) - 1
    sharpe = ret.mean() / ret.std() * (252 ** 0.5)
    max_dd = (prices / prices.cummax() - 1).min()
    return {"cagr": cagr, "sharpe": sharpe, "max_dd": max_dd}


def sweep(prices, label):
    results = []
    combos = [(f, s) for f, s in itertools.product(FAST_WINDOWS, SLOW_WINDOWS) if f < s]

    for fast, slow in combos:
        if len(prices) < slow + 10:
            continue
        m = simulate(prices, fast, slow)
        m["fast"] = fast
        m["slow"] = slow
        results.append(m)

    df = pd.DataFrame(results)

    # Apply hard constraints
    passing = df[
        (df["max_dd"] >= MAX_DRAWDOWN_LIMIT) &
        (df["margin_calls"] <= MAX_MARGIN_CALLS)
    ].copy()

    passing.sort_values("cagr", ascending=False, inplace=True)

    print(f"\n{'─'*60}")
    print(f"  {label}")
    print(f"{'─'*60}")
    print(f"  Combinations tested : {len(df)}")
    print(f"  Passing constraints : {len(passing)}  "
          f"(max_dd > {MAX_DRAWDOWN_LIMIT:.0%}, margin calls = 0)")

    if passing.empty:
        print("  No combinations passed. Consider relaxing constraints.")
        return pd.DataFrame()

    print(f"\n  Top {min(TOP_N, len(passing))} by CAGR (in-sample):\n")
    print(f"  {'MA':>10} {'CAGR':>8} {'Sharpe':>8} {'MaxDD':>8} {'Fees':>8}")
    print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for _, row in passing.head(TOP_N).iterrows():
        print(f"  {int(row.fast)}/{int(row.slow):>6}     "
              f"{row.cagr:>7.1%}  {row.sharpe:>7.2f}  {row.max_dd:>7.1%}  ${row.total_fees:>6.0f}")

    return passing.head(TOP_N)[["fast", "slow"]]


def validate(prices, top_params, label):
    if top_params.empty:
        return

    bah = bah_metrics(prices)
    print(f"\n  Out-of-sample validation — {label}")
    print(f"\n  {'MA':>10} {'CAGR':>8} {'Sharpe':>8} {'MaxDD':>8} {'vs B&H CAGR':>12} {'Pass?':>6}")
    print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*12} {'-'*6}")

    for _, row in top_params.iterrows():
        fast, slow = int(row.fast), int(row.slow)
        if len(prices) < slow + 10:
            continue
        m = simulate(prices, fast, slow)
        passes = (m["max_dd"] >= MAX_DRAWDOWN_LIMIT and m["margin_calls"] <= MAX_MARGIN_CALLS)
        flag = "YES" if passes else "NO"
        diff = m["cagr"] - bah["cagr"]
        print(f"  {fast}/{slow:>6}     "
              f"{m['cagr']:>7.1%}  {m['sharpe']:>7.2f}  {m['max_dd']:>7.1%}  "
              f"{diff:>+11.1%}  {flag:>6}")

    print(f"\n  Buy & Hold (OOS): CAGR {bah['cagr']:.1%}, "
          f"Sharpe {bah['sharpe']:.2f}, MaxDD {bah['max_dd']:.1%}")


def run(tickers):
    print(f"\nFetching data for: {', '.join(tickers)}...")
    print(f"In-sample  : {IN_SAMPLE_START} → {IN_SAMPLE_END}")
    print(f"Out-of-sample: {OOS_START} → present")

    for ticker in tickers:
        raw = yf.download(ticker, start=IN_SAMPLE_START, auto_adjust=True, progress=False)
        prices_all = raw["Close"].squeeze().dropna()

        prices_in  = prices_all[prices_all.index <= IN_SAMPLE_END]
        prices_oos = prices_all[prices_all.index >= OOS_START]

        print(f"\n{'='*60}")
        print(f"  {ticker}  —  {len(prices_in)} in-sample days, {len(prices_oos)} OOS days")
        print(f"{'='*60}")

        top_params = sweep(prices_in, f"{ticker} in-sample ({IN_SAMPLE_START}–{IN_SAMPLE_END})")
        validate(prices_oos, top_params, f"{ticker} ({OOS_START}–present)")


if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_TICKERS
    run(tickers)
