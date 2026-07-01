"""
Core portfolio simulator.

Takes a price series and a positions series (target leverage per day),
runs the day-by-day simulation applying returns, borrow costs, trade fees,
and margin call logic.

positions: pd.Series aligned to prices
  - values are target leverage: 1.0 = no margin, 2.0 = full margin
  - index must be a subset of prices.index
"""

import pandas as pd
from core.config import (
    MARGIN_RATE, INITIAL_CAPITAL, MAINTENANCE_MARGIN,
    FEE_PER_SHARE, FEE_MIN_PER_ORDER
)


def _trade_fee(shares: float) -> float:
    return max(shares * FEE_PER_SHARE, FEE_MIN_PER_ORDER)


def run(prices: pd.Series, positions: pd.Series) -> dict:
    """
    Simulate portfolio given daily target leverage positions.

    Returns dict with:
      equity       pd.Series  — daily portfolio value
      leverage     pd.Series  — daily effective leverage
      margin_calls int        — number of margin call events
      total_fees   float      — total fees paid
    """
    # Align prices to positions (positions may start later due to signal warmup)
    prices = prices.reindex(positions.index).dropna()
    positions = positions.reindex(prices.index)

    daily_borrow_rate = MARGIN_RATE / 252
    equity = INITIAL_CAPITAL
    current_leverage = 1.0
    margin_calls = 0
    total_fees = 0.0
    equity_curve = []
    leverage_curve = []
    prev_price = None

    for date, price in prices.items():
        target_leverage = positions.loc[date]

        if prev_price is not None:
            daily_ret = (price - prev_price) / prev_price
            borrowed = current_leverage - 1.0
            equity *= 1 + current_leverage * daily_ret - borrowed * daily_borrow_rate

        # Trade fee on leverage change
        if target_leverage != current_leverage and price > 0:
            shares = abs(equity * target_leverage - equity * current_leverage) / price
            fee = _trade_fee(shares)
            equity -= fee
            total_fees += fee

        # Margin call check
        position_value = equity * target_leverage
        equity_ratio = equity / position_value if position_value > 0 else 1.0

        if equity_ratio < MAINTENANCE_MARGIN and equity > 0:
            forced = max(1.0, min(target_leverage, 1.0 / MAINTENANCE_MARGIN))
            shares = abs(equity * target_leverage - equity * forced) / price
            fee = _trade_fee(shares)
            equity -= fee
            total_fees += fee
            current_leverage = forced
            margin_calls += 1
        else:
            current_leverage = target_leverage

        equity_curve.append(equity)
        leverage_curve.append(current_leverage)
        prev_price = price

    return {
        "equity":       pd.Series(equity_curve, index=prices.index),
        "leverage":     pd.Series(leverage_curve, index=prices.index),
        "margin_calls": margin_calls,
        "total_fees":   total_fees,
    }
