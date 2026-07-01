"""Simulator: fee, borrow-cost, and equity math on hand-computable scenarios.

These pin down the exact daily accounting so refactors can't silently change
the numbers that live signals and backtests are built on.
"""

import pandas as pd
import pytest

from core.config import MARGIN_RATE, FEE_PER_SHARE, FEE_MIN_PER_ORDER
from core.simulator import run

DAILY_BORROW = MARGIN_RATE / 252


def _flat_prices(n, price=100.0):
    return pd.Series([price] * n, index=pd.bdate_range("2024-01-01", periods=n))


def test_unleveraged_flat_market_is_a_noop():
    prices = _flat_prices(10)
    pos = pd.Series(1.0, index=prices.index)
    res = run(prices, pos, capital=10_000)
    assert (res["equity"] == 10_000).all()
    assert res["total_fees"] == 0
    assert res["margin_calls"] == 0


def test_levering_up_charges_one_fee_then_daily_borrow():
    n = 10
    prices = _flat_prices(n, price=100.0)
    pos = pd.Series(2.0, index=prices.index)
    res = run(prices, pos, capital=10_000)

    # Day 0: leverage 1 -> 2 buys equity/price = 100 shares
    fee = max(100 * FEE_PER_SHARE, FEE_MIN_PER_ORDER)
    assert res["total_fees"] == pytest.approx(fee)

    # Days 1..n-1: flat price, borrow cost on 1x borrowed portion
    expected_final = (10_000 - fee) * (1 - DAILY_BORROW) ** (n - 1)
    assert res["equity"].iloc[-1] == pytest.approx(expected_final)
    assert res["margin_calls"] == 0


def test_leveraged_return_is_double_minus_borrow():
    prices = pd.Series([100.0, 110.0], index=pd.bdate_range("2024-01-01", periods=2))
    pos = pd.Series(2.0, index=prices.index)
    res = run(prices, pos, capital=10_000)

    fee = max(100 * FEE_PER_SHARE, FEE_MIN_PER_ORDER)
    expected = (10_000 - fee) * (1 + 2 * 0.10 - 1 * DAILY_BORROW)
    assert res["equity"].iloc[-1] == pytest.approx(expected)


def test_min_fee_applies_to_small_orders():
    prices = _flat_prices(2, price=100.0)
    pos = pd.Series(2.0, index=prices.index)
    res = run(prices, pos, capital=1_000)   # 10 shares -> below min fee
    assert res["total_fees"] == pytest.approx(FEE_MIN_PER_ORDER)


def test_deleveraging_also_pays_a_fee():
    prices = _flat_prices(4, price=100.0)
    pos = pd.Series([2.0, 2.0, 1.0, 1.0], index=prices.index)
    res = run(prices, pos, capital=10_000)
    assert res["total_fees"] > FEE_MIN_PER_ORDER  # one fee up, one fee down
    # After deleveraging, no further borrow cost accrues
    assert res["equity"].iloc[-1] == pytest.approx(res["equity"].iloc[-2])


def test_two_x_never_triggers_margin_call():
    # Simulator re-levers daily, so equity ratio at 2x is a constant 0.5 > 0.30
    prices = pd.Series(
        [100, 80, 60, 45, 30],
        index=pd.bdate_range("2024-01-01", periods=5), dtype=float,
    )
    pos = pd.Series(2.0, index=prices.index)
    res = run(prices, pos, capital=10_000)
    assert res["margin_calls"] == 0
