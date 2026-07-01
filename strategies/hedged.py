"""
Hedged momentum strategy.

When signal is bullish  → hold main asset at LEVERAGE x (with margin)
When signal is bearish  → hold hedge asset at HEDGE_FRACTION x (no margin)

Default hedge: SH (ProShares Short S&P500, -1x SPY). Buyable on Futu HK.

Fees charged on every asset transition (sell + buy).
Margin calls modelled only during the leveraged long phase.
"""

import pandas as pd
from core.config import (
    LEVERAGE, MARGIN_RATE, INITIAL_CAPITAL, MAINTENANCE_MARGIN,
    FEE_PER_SHARE, FEE_MIN_PER_ORDER
)

HEDGE_TICKER   = "SH"    # ProShares Short S&P500
HEDGE_FRACTION = 1.0     # fraction of equity to put into hedge asset


def _fee(shares: float) -> float:
    return max(shares * FEE_PER_SHARE, FEE_MIN_PER_ORDER)


def run(main_prices: pd.Series, hedge_prices: pd.Series,
        signal: pd.Series, leverage: float = LEVERAGE,
        hedge_fraction: float = HEDGE_FRACTION) -> dict:
    """
    Simulate hedged strategy across two assets.

    Returns same dict as core.simulator.run():
      equity, leverage (series), margin_calls, total_fees
    """
    df = pd.concat(
        [main_prices.rename("main"), hedge_prices.rename("hedge"), signal.rename("signal")],
        axis=1, join="inner"
    ).dropna()

    daily_borrow = MARGIN_RATE / 252
    equity       = INITIAL_CAPITAL
    state        = None   # None | "long" | "hedge"
    total_fees   = 0.0
    margin_calls = 0

    equity_curve  = []
    leverage_curve = []
    prev = None

    for date, row in df.iterrows():
        mp   = row["main"]
        hp   = row["hedge"]
        sig  = int(row["signal"])
        target = "long" if sig == 1 else "hedge"

        # Apply yesterday's position return
        if prev is not None:
            if state == "long":
                ret = (mp - prev["main"]) / prev["main"]
                borrowed = leverage - 1.0
                equity *= 1 + leverage * ret - borrowed * daily_borrow
            elif state == "hedge":
                ret = (hp - prev["hedge"]) / prev["hedge"]
                equity *= 1 + hedge_fraction * ret

        # Transition fees
        if target != state:
            if state == "long" and mp > 0:
                fee = _fee(equity * leverage / mp)
                equity -= fee; total_fees += fee
            if state == "hedge" and hp > 0:
                fee = _fee(equity * hedge_fraction / hp)
                equity -= fee; total_fees += fee
            if target == "long" and mp > 0:
                fee = _fee(equity * leverage / mp)
                equity -= fee; total_fees += fee
            if target == "hedge" and hp > 0:
                fee = _fee(equity * hedge_fraction / hp)
                equity -= fee; total_fees += fee
            state = target

        # Margin call during long phase
        if state == "long":
            pos_value = equity * leverage
            eq_ratio  = equity / pos_value if pos_value > 0 else 1.0
            if eq_ratio < MAINTENANCE_MARGIN and equity > 0:
                forced = max(1.0, min(leverage, 1.0 / MAINTENANCE_MARGIN))
                fee = _fee(abs(equity * leverage - equity * forced) / mp)
                equity -= fee; total_fees += fee
                state = "hedge" if forced == 1.0 else "long"
                margin_calls += 1

        equity_curve.append(max(equity, 0))
        leverage_curve.append(leverage if state == "long" else -hedge_fraction)
        prev = row

    idx = df.index[:len(equity_curve)]
    return {
        "equity":       pd.Series(equity_curve, index=idx),
        "leverage":     pd.Series(leverage_curve, index=idx),
        "margin_calls": margin_calls,
        "total_fees":   total_fees,
    }
