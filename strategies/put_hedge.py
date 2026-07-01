"""
Put options hedge strategy.

When signal is bullish  → hold main asset at LEVERAGE x (with margin)
When signal is bearish  → sell main asset, buy ATM put options + hold rest in cash

Put model:
  - Buy 1-month ATM puts when signal flips bearish
  - Roll every PUT_DAYS trading days while signal stays bearish
  - Price with Black-Scholes using 30-day realized volatility
  - PUT_ALLOC% of equity spent on premium each roll; remainder is cash
  - Daily P&L = num_puts * (new_bs_price - prev_bs_price)

Simplifications: no bid-ask spread, no early exercise, no dividends.
"""

import numpy as np
import pandas as pd
from scipy.stats import norm

from core.config import (
    LEVERAGE, MARGIN_RATE, INITIAL_CAPITAL, MAINTENANCE_MARGIN,
    FEE_PER_SHARE, FEE_MIN_PER_ORDER
)

PUT_ALLOC  = 0.05    # fraction of equity spent on put premium per roll
PUT_DAYS   = 21      # put duration in trading days (~1 month)
RISK_FREE  = 0.05    # annual risk-free rate
VOL_WINDOW = 30      # days for realized vol estimate


def _fee(shares: float) -> float:
    return max(shares * FEE_PER_SHARE, FEE_MIN_PER_ORDER)


def _bs_put(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes European put price per unit of underlying."""
    if T <= 0:
        return max(K - S, 0.0)
    sigma = max(sigma, 0.05)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def run(prices: pd.Series, signal: pd.Series,
        leverage: float = LEVERAGE) -> dict:

    log_ret      = np.log(prices / prices.shift(1))
    realized_vol = log_ret.rolling(VOL_WINDOW).std() * np.sqrt(252)

    df = pd.concat(
        [prices.rename("price"), signal.rename("signal"), realized_vol.rename("vol")],
        axis=1, join="inner"
    ).dropna()

    daily_borrow  = MARGIN_RATE / 252
    equity        = INITIAL_CAPITAL
    state         = None          # None | "long" | "put"
    total_fees    = 0.0
    margin_calls  = 0

    # Put state — fixed at purchase
    num_puts      = 0.0   # number of put contracts (1 unit = 1 share equivalent)
    put_strike    = 0.0
    put_days_left = 0
    prev_put_val  = 0.0   # BS value of ONE put on previous day

    equity_curve  = []
    leverage_curve = []
    prev_price    = None

    for date, row in df.iterrows():
        price  = row["price"]
        sig    = int(row["signal"])
        vol    = max(row["vol"], 0.05)
        target = "long" if sig == 1 else "put"

        # --- Apply yesterday's return ---
        if prev_price is not None:
            if state == "long":
                ret      = (price - prev_price) / prev_price
                borrowed = leverage - 1.0
                equity  *= 1 + leverage * ret - borrowed * daily_borrow

            elif state == "put" and num_puts > 0 and put_days_left > 0:
                T_today  = put_days_left / 252
                cur_val  = _bs_put(price, put_strike, T_today, RISK_FREE, vol)
                equity  += num_puts * (cur_val - prev_put_val)
                prev_put_val  = cur_val
                put_days_left -= 1

        # --- Transitions ---
        if target != state:
            # Close current position
            if state == "long" and price > 0:
                fee = _fee(equity * leverage / price)
                equity -= fee; total_fees += fee

            elif state == "put" and num_puts > 0:
                # Collect intrinsic value at close
                intrinsic = max(put_strike - price, 0.0)
                equity   += num_puts * intrinsic
                # Sell the puts (fee on notional shares)
                fee = _fee(num_puts)
                equity -= fee; total_fees += fee
                num_puts = put_days_left = 0; prev_put_val = 0.0

            # Open new position
            if target == "long" and price > 0:
                fee = _fee(equity * leverage / price)
                equity -= fee; total_fees += fee

            elif target == "put" and price > 0:
                premium_budget = equity * PUT_ALLOC
                T = PUT_DAYS / 252
                put_price = _bs_put(price, price, T, RISK_FREE, vol)
                if put_price > 0:
                    num_puts  = premium_budget / put_price
                    equity   -= premium_budget
                    put_strike    = price
                    put_days_left = PUT_DAYS
                    prev_put_val  = put_price
                    fee = _fee(num_puts)
                    equity -= fee; total_fees += fee

            state = target

        # --- Roll put if expired while still bearish ---
        elif state == "put" and put_days_left <= 0:
            # Collect expiry intrinsic value
            intrinsic = max(put_strike - price, 0.0)
            equity   += num_puts * intrinsic

            # Buy new put
            premium_budget = equity * PUT_ALLOC
            T = PUT_DAYS / 252
            put_price = _bs_put(price, price, T, RISK_FREE, vol)
            if put_price > 0:
                num_puts      = premium_budget / put_price
                equity       -= premium_budget
                put_strike    = price
                put_days_left = PUT_DAYS
                prev_put_val  = put_price
                fee = _fee(num_puts)
                equity -= fee; total_fees += fee
            else:
                num_puts = 0

        # --- Margin call during long phase ---
        if state == "long" and price > 0:
            pos_value = equity * leverage
            eq_ratio  = equity / pos_value if pos_value > 0 else 1.0
            if eq_ratio < MAINTENANCE_MARGIN and equity > 0:
                forced = max(1.0, min(leverage, 1.0 / MAINTENANCE_MARGIN))
                fee    = _fee(abs(equity * leverage - equity * forced) / price)
                equity -= fee; total_fees += fee
                margin_calls += 1

        equity_curve.append(max(equity, 0.0))
        leverage_curve.append(leverage if state == "long" else 0.0)
        prev_price = price

    idx = df.index[:len(equity_curve)]
    return {
        "equity":       pd.Series(equity_curve, index=idx),
        "leverage":     pd.Series(leverage_curve, index=idx),
        "margin_calls": margin_calls,
        "total_fees":   total_fees,
    }
