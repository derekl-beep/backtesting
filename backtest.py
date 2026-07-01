"""
Momentum-based margin strategy backtest.

Usage:
  python backtest.py                        # default tickers
  python backtest.py SPMO QQQ SPY          # compare specific tickers

Strategy per ticker:
  - When MA_FAST > MA_SLOW: hold at LEVERAGE x using margin
  - When MA_FAST < MA_SLOW: hold at 1x (no margin)
  - Optional VIX filter: block margin when VIX >= VIX_THRESHOLD
  - Margin call: force-reduce position if equity ratio < MAINTENANCE_MARGIN
"""

import sys
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

# --- Config ---
DEFAULT_TICKERS = ["SPMO", "QQQ", "SPY"]
START = "2020-01-01"
LEVERAGE = 2.0
MARGIN_RATE = 0.048
INITIAL_CAPITAL = 10_000
MAINTENANCE_MARGIN = 0.30
MA_FAST = 50
MA_SLOW = 100
VIX_THRESHOLD = None       # set to a number (e.g. 25) to block margin when VIX >= threshold

FEE_PER_SHARE = 0.0049 + 0.005
FEE_MIN_PER_ORDER = 0.99 + 1.00


def calc_trade_fee(shares):
    return max(shares * FEE_PER_SHARE, FEE_MIN_PER_ORDER)


def simulate(prices, vix=None):
    df = pd.DataFrame({"price": prices})
    df["ma_fast"] = df["price"].rolling(MA_FAST).mean()
    df["ma_slow"] = df["price"].rolling(MA_SLOW).mean()
    df.dropna(inplace=True)

    df["ma_signal"] = (df["ma_fast"] > df["ma_slow"]).astype(int)

    if vix is not None and VIX_THRESHOLD is not None:
        df = df.join(vix.rename("vix"), how="left")
        df["vix"] = df["vix"].ffill()
        df["signal"] = ((df["ma_fast"] > df["ma_slow"]) & (df["vix"] < VIX_THRESHOLD)).astype(int)
    else:
        df["signal"] = df["ma_signal"]

    df.dropna(inplace=True)

    daily_borrow_rate = MARGIN_RATE / 252
    equity = INITIAL_CAPITAL
    current_leverage = 1.0
    margin_calls = 0
    total_fees = 0.0
    equity_curve = []
    leverage_curve = []
    margin_call_dates = []
    prev_price = None

    for date, row in df.iterrows():
        price = row["price"]
        signal = row["signal"]

        if prev_price is not None:
            daily_ret = (price - prev_price) / prev_price
            borrowed_fraction = current_leverage - 1.0
            strategy_ret = current_leverage * daily_ret - borrowed_fraction * daily_borrow_rate
            equity = equity * (1 + strategy_ret)

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
            margin_call_dates.append(date)
        else:
            current_leverage = target_leverage

        equity_curve.append(equity)
        leverage_curve.append(current_leverage)
        prev_price = price

    df = df.iloc[:len(equity_curve)].copy()
    df["equity"] = equity_curve
    df["effective_leverage"] = leverage_curve

    return df, margin_calls, total_fees


def calc_metrics(equity_series):
    ret = equity_series.pct_change().dropna()
    n_years = len(ret) / 252
    total = equity_series.iloc[-1] / equity_series.iloc[0] - 1
    cagr = (1 + total) ** (1 / n_years) - 1
    sharpe = ret.mean() / ret.std() * (252 ** 0.5)
    max_dd = (equity_series / equity_series.cummax() - 1).min()
    return {"total": total, "cagr": cagr, "sharpe": sharpe, "max_dd": max_dd}


def run_backtest(tickers):
    print(f"Fetching data for: {', '.join(tickers)} + VIX...")
    vix_raw = yf.download("^VIX", start=START, auto_adjust=True, progress=False)
    vix = vix_raw["Close"].squeeze().dropna() if VIX_THRESHOLD is not None else None

    all_results = []

    for ticker in tickers:
        raw = yf.download(ticker, start=START, auto_adjust=True, progress=False)
        prices = raw["Close"].squeeze().dropna()

        if len(prices) < MA_SLOW + 10:
            print(f"\n{ticker}: not enough data, skipping.")
            continue

        # Buy & hold baseline (aligned to warmup period)
        bah_prices = prices.iloc[MA_SLOW - 1:]
        bah_equity = INITIAL_CAPITAL * (bah_prices / bah_prices.iloc[0])
        bah_m = calc_metrics(bah_equity)

        # Strategy
        df, margin_calls, total_fees = simulate(prices, vix=vix)
        strat_m = calc_metrics(df["equity"])

        all_results.append({
            "ticker": ticker,
            "bah_equity": bah_equity,
            "bah_m": bah_m,
            "strat_equity": df["equity"],
            "strat_m": strat_m,
            "margin_calls": margin_calls,
            "total_fees": total_fees,
        })

        print(f"\n{'='*40}")
        print(f" {ticker}")
        print(f"{'='*40}")
        print(f"  {'':30s} {'Buy&Hold':>10} {'Strategy':>10}")
        print(f"  {'Total return':30s} {bah_m['total']:>10.1%} {strat_m['total']:>10.1%}")
        print(f"  {'CAGR':30s} {bah_m['cagr']:>10.1%} {strat_m['cagr']:>10.1%}")
        print(f"  {'Sharpe ratio':30s} {bah_m['sharpe']:>10.2f} {strat_m['sharpe']:>10.2f}")
        print(f"  {'Max drawdown':30s} {bah_m['max_dd']:>10.1%} {strat_m['max_dd']:>10.1%}")
        print(f"  {'Margin calls':30s} {'':>10} {margin_calls:>10}")
        print(f"  {'Total fees':30s} {'':>10} ${total_fees:>9,.2f}")

    if not all_results:
        print("No valid results.")
        return

    # Plot
    n = len(all_results)
    fig, axes = plt.subplots(n, 1, figsize=(13, 4 * n), squeeze=False)

    colors = ["darkorange", "green", "crimson", "purple", "brown"]

    for i, r in enumerate(all_results):
        ax = axes[i][0]
        ticker = r["ticker"]
        color = colors[i % len(colors)]

        ax.plot(r["bah_equity"].index, r["bah_equity"].values,
                label=f"{ticker} Buy & Hold", color="steelblue", linewidth=1.5)
        ax.plot(r["strat_equity"].index, r["strat_equity"].values,
                label=f"{ticker} Strategy ({LEVERAGE}x)", color=color, linewidth=1.5)

        bah_m = r["bah_m"]
        strat_m = r["strat_m"]
        summary = (
            f"B&H: CAGR {bah_m['cagr']:.1%}, Sharpe {bah_m['sharpe']:.2f}, MaxDD {bah_m['max_dd']:.1%}   |   "
            f"Strategy: CAGR {strat_m['cagr']:.1%}, Sharpe {strat_m['sharpe']:.2f}, MaxDD {strat_m['max_dd']:.1%}"
        )
        ax.set_title(f"{ticker} — {summary}", fontsize=9)
        ax.set_ylabel("Portfolio Value ($)")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    vix_label = f"VIX<{VIX_THRESHOLD} filter ON" if VIX_THRESHOLD else "VIX filter OFF"
    fig.suptitle(
        f"Momentum Margin Strategy: MA {MA_FAST}/{MA_SLOW}, {LEVERAGE}x, "
        f"{MARGIN_RATE:.1%} borrow, {vix_label}",
        fontsize=11, y=1.01
    )

    plt.tight_layout()
    out = "backtest_results.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to {out}")
    plt.show()


if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_TICKERS
    run_backtest(tickers)
