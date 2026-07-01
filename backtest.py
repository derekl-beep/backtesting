"""
SPMO momentum-based margin strategy backtest.

Strategy:
  - When fast MA > slow MA AND VIX < VIX_THRESHOLD: hold SPMO at LEVERAGE x using margin
  - When fast MA > slow MA BUT VIX >= VIX_THRESHOLD: hold 1x (volatility filter blocks margin)
  - When fast MA < slow MA: hold 1x (no margin)
  - Margin borrow cost applied daily on the borrowed portion
  - Margin call triggered when equity / position value falls below MAINTENANCE_MARGIN
"""

import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

# --- Config ---
TICKER = "SPMO"
START = "2012-01-01"
LEVERAGE = 2.0
MARGIN_RATE = 0.048        # annual borrow rate (Futu HK USD rate)
INITIAL_CAPITAL = 10_000
MAINTENANCE_MARGIN = 0.30  # Futu ~30% equity ratio; margin call below this
MA_FAST = 50
MA_SLOW = 200
VIX_THRESHOLD = 25         # block margin when VIX >= this level

# Futu HK fee structure (per trade, applied on signal flips)
FEE_PER_SHARE = 0.0049 + 0.005   # commission + platform fee = $0.0099/share
FEE_MIN_PER_ORDER = 0.99 + 1.00  # min commission + min platform fee = $1.99/order


def calc_trade_fee(shares):
    return max(shares * FEE_PER_SHARE, FEE_MIN_PER_ORDER)


def simulate(prices, ma_fast, ma_slow, leverage, margin_rate, initial_capital,
             maintenance_margin, vix=None, vix_threshold=None):
    df = pd.DataFrame({"price": prices})
    df["ma_fast"] = df["price"].rolling(ma_fast).mean()
    df["ma_slow"] = df["price"].rolling(ma_slow).mean()
    df.dropna(inplace=True)

    df["ma_signal"] = (df["ma_fast"] > df["ma_slow"]).astype(int)

    # Merge VIX if provided
    if vix is not None and vix_threshold is not None:
        df = df.join(vix.rename("vix"), how="left")
        df["vix"] = df["vix"].ffill()
        df["vix_ok"] = (df["vix"] < vix_threshold).astype(int)
        df["signal"] = df["ma_signal"] & df["vix_ok"]
    else:
        df["signal"] = df["ma_signal"]

    df.dropna(inplace=True)

    daily_borrow_rate = margin_rate / 252

    equity = initial_capital
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

        target_leverage = leverage if signal == 1 else 1.0

        # Trade fee on leverage change
        if target_leverage != current_leverage and price > 0:
            shares_traded = abs(equity * target_leverage - equity * current_leverage) / price
            fee = calc_trade_fee(shares_traded)
            equity -= fee
            total_fees += fee

        # Margin call check
        position_value = equity * target_leverage
        equity_ratio = equity / position_value if position_value > 0 else 1.0

        if equity_ratio < maintenance_margin and equity > 0:
            forced_leverage = min(target_leverage, 1.0 / maintenance_margin)
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

    return df, margin_calls, margin_call_dates, total_fees


def metrics(equity_series, label):
    ret = equity_series.pct_change().dropna()
    n_years = len(ret) / 252
    total = equity_series.iloc[-1] / equity_series.iloc[0] - 1
    cagr = (1 + total) ** (1 / n_years) - 1
    sharpe = ret.mean() / ret.std() * (252 ** 0.5)
    drawdown = equity_series / equity_series.cummax() - 1
    max_dd = drawdown.min()
    print(f"\n{label}")
    print(f"  Total return : {total:.1%}")
    print(f"  CAGR         : {cagr:.1%}")
    print(f"  Sharpe ratio : {sharpe:.2f}")
    print(f"  Max drawdown : {max_dd:.1%}")
    return {"total": total, "cagr": cagr, "sharpe": sharpe, "max_dd": max_dd}


def run_backtest():
    print(f"Fetching {TICKER} and VIX data...")
    raw = yf.download(TICKER, start=START, auto_adjust=True, progress=False)
    prices = raw["Close"].squeeze().dropna()

    vix_raw = yf.download("^VIX", start=START, auto_adjust=True, progress=False)
    vix = vix_raw["Close"].squeeze().dropna()

    configs = [
        {
            "label": f"MA {MA_FAST}/{MA_SLOW}",
            "fast": MA_FAST, "slow": MA_SLOW,
            "vix": None, "color": "darkorange"
        },
        {
            "label": "MA 20/50",
            "fast": 20, "slow": 50,
            "vix": None, "color": "green"
        },
        {
            "label": f"MA 20/50 + VIX<{VIX_THRESHOLD} filter",
            "fast": 20, "slow": 50,
            "vix": vix, "color": "crimson"
        },
    ]

    # Buy & hold baseline (align start to longest warmup)
    bah_prices = prices[prices.index >= prices.index[MA_SLOW - 1]]
    bah_equity = INITIAL_CAPITAL * (bah_prices / bah_prices.iloc[0])

    print("\n=== Backtest Results ===")
    metrics(bah_equity, "Buy & Hold SPMO")

    results = []
    for cfg in configs:
        df, mc_count, mc_dates, total_fees = simulate(
            prices, cfg["fast"], cfg["slow"],
            LEVERAGE, MARGIN_RATE, INITIAL_CAPITAL, MAINTENANCE_MARGIN,
            vix=cfg["vix"], vix_threshold=VIX_THRESHOLD if cfg["vix"] is not None else None
        )
        label = f"{cfg['label']} ({LEVERAGE}x margin)"
        m = metrics(df["equity"], label)
        print(f"  Margin calls : {mc_count}")
        print(f"  Total fees   : ${total_fees:,.2f}")
        if mc_dates:
            print(f"  First call   : {mc_dates[0].date()}")
        results.append((cfg["label"], df, mc_dates, m, cfg["color"]))

    # Plot
    fig, axes = plt.subplots(3, 1, figsize=(13, 10), gridspec_kw={"height_ratios": [3, 1, 1]})

    ax1 = axes[0]
    ax1.plot(bah_equity.index, bah_equity.values, label="Buy & Hold", color="steelblue", linewidth=1.5)
    for label, df, mc_dates, _, color in results:
        ax1.plot(df.index, df["equity"], label=label, color=color, linewidth=1.5)
        for d in mc_dates:
            ax1.axvline(d, color=color, alpha=0.3, linewidth=0.8, linestyle="--")
    ax1.set_title(f"SPMO: Buy & Hold vs Margin Strategies ({LEVERAGE}x, {MARGIN_RATE:.1%} borrow, VIX threshold={VIX_THRESHOLD})")
    ax1.set_ylabel("Portfolio Value ($)")
    ax1.legend()
    ax1.grid(alpha=0.3)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # VIX panel
    ax2 = axes[1]
    ax2.plot(vix.index, vix.values, color="purple", linewidth=1.0, label="VIX")
    ax2.axhline(VIX_THRESHOLD, color="red", linewidth=1.0, linestyle="--", label=f"Threshold ({VIX_THRESHOLD})")
    ax2.fill_between(vix.index, vix.values, VIX_THRESHOLD,
                     where=(vix.values >= VIX_THRESHOLD), alpha=0.2, color="red", label="Margin blocked")
    ax2.set_ylabel("VIX")
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(alpha=0.3)

    # Leverage panel for VIX-filtered strategy
    ax3 = axes[2]
    _, df_vix, _, _, _ = results[2]
    ax3.fill_between(df_vix.index, df_vix["effective_leverage"], 1,
                     alpha=0.4, color="crimson", step="post", label="Leverage in use")
    ax3.set_ylabel("Leverage\n(VIX-filtered)")
    ax3.set_ylim(0.8, LEVERAGE + 0.2)
    ax3.axhline(1.0, color="gray", linewidth=0.8, linestyle="--")
    ax3.set_xlabel("Date")
    ax3.legend(loc="upper left", fontsize=8)
    ax3.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig("backtest_results.png", dpi=150)
    print("\nChart saved to backtest_results.png")
    plt.show()


if __name__ == "__main__":
    run_backtest()
