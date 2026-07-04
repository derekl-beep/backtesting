"""
Options-overlay engine: Black-Scholes math, regime extraction, and the
per-regime rolling simulator. None of tools/options_backtest.py had any
test coverage before this -- these pin the core math and the exact
"budget can't cover 1 contract -> skip the trade" behavior fixed after it
was found silently overspending past the requested budget fraction.
"""

import math

import pandas as pd
import pytest

from tools.options_backtest import (
    ROLL_DTE, TENOR_DAYS,
    _get_regimes, _realized_vol, bs_call, bs_delta, simulate_regime,
    simulate_regime_with_rolls, strike_for_delta,
)


# ---------------------------------------------------------------------------
# Black-Scholes math
# ---------------------------------------------------------------------------

def test_bs_call_matches_textbook_reference():
    # Classic reference case (S=K=100, T=1y, r=5%, sigma=20%) -> ~10.4506
    price = bs_call(100, 100, 1, 0.05, 0.20)
    assert price == pytest.approx(10.4506, abs=1e-3)


def test_bs_call_at_expiry_is_intrinsic_value():
    assert bs_call(110, 100, 0, 0.05, 0.20) == pytest.approx(10.0)
    assert bs_call(90, 100, 0, 0.05, 0.20) == pytest.approx(0.0)


def test_bs_call_with_zero_vol_is_intrinsic_value():
    assert bs_call(110, 100, 1, 0.05, 0.0) == pytest.approx(10.0)


def test_bs_delta_is_bounded_and_increases_with_moneyness():
    itm = bs_delta(120, 100, 0.5, 0.05, 0.20)
    atm = bs_delta(100, 100, 0.5, 0.05, 0.20)
    otm = bs_delta(80, 100, 0.5, 0.05, 0.20)
    assert 0.0 < otm < atm < itm < 1.0


def test_strike_for_delta_round_trips_through_bs_delta():
    S, T, r, sigma = 100, 1, 0.05, 0.20
    for target in (0.30, 0.50, 0.70, 0.85):
        K = strike_for_delta(S, T, r, sigma, target)
        assert bs_delta(S, K, T, r, sigma) == pytest.approx(target, abs=1e-3)


def test_strike_for_delta_higher_delta_means_lower_strike():
    S, T, r, sigma = 100, 1, 0.05, 0.20
    k_deep_itm = strike_for_delta(S, T, r, sigma, 0.85)
    k_atm      = strike_for_delta(S, T, r, sigma, 0.50)
    k_otm      = strike_for_delta(S, T, r, sigma, 0.30)
    assert k_deep_itm < k_atm < k_otm


# ---------------------------------------------------------------------------
# Regime extraction
# ---------------------------------------------------------------------------

def _signal(values):
    idx = pd.bdate_range("2024-01-01", periods=len(values))
    return pd.Series(values, index=idx, dtype=float)


def test_get_regimes_starts_bullish():
    sig = _signal([1, 1, 1, 0, 0, 1, 1])
    regimes = _get_regimes(sig)
    assert len(regimes) == 2
    assert regimes[0] == (sig.index[0], sig.index[3])
    assert regimes[1] == (sig.index[5], sig.index[-1])


def test_get_regimes_starts_bearish():
    sig = _signal([0, 0, 1, 1, 0])
    regimes = _get_regimes(sig)
    assert len(regimes) == 1
    assert regimes[0] == (sig.index[2], sig.index[-1])


def test_get_regimes_never_bullish_is_empty():
    sig = _signal([0, 0, 0, 0])
    assert _get_regimes(sig) == []


def test_get_regimes_ongoing_regime_ends_at_last_date():
    sig = _signal([0, 1, 1, 1])
    regimes = _get_regimes(sig)
    assert regimes == [(sig.index[1], sig.index[-1])]


# ---------------------------------------------------------------------------
# Per-regime simulation
# ---------------------------------------------------------------------------

def _flat_prices(n, price, start="2024-01-01"):
    return pd.Series([price] * n, index=pd.bdate_range(start, periods=n))


def _flat_iv(n, pct, start="2024-01-01"):
    return pd.Series([pct] * n, index=pd.bdate_range(start, periods=n))


def test_simulate_regime_rising_underlying_is_profitable():
    n = 200
    prices = pd.Series(
        [100 + i * 0.5 for i in range(n)],
        index=pd.bdate_range("2024-01-01", periods=n),
    )
    iv = _flat_iv(n, 20.0)
    result = simulate_regime(prices.index[0], prices.index[-1], prices, iv,
                             target_delta=0.50, budget_frac=0.05, capital=100_000)
    assert result is not None
    assert result["return_on_premium"] > 0
    assert result["n_contracts"] >= 1


def test_simulate_regime_budget_too_small_returns_none():
    # A tiny budget against an expensive premium must not silently overspend
    # past the requested budget_frac by forcing a minimum of 1 contract.
    n = 200
    prices = _flat_prices(n, 500.0)   # high-priced underlying -> expensive premium
    iv = _flat_iv(n, 80.0)            # high vol -> expensive premium
    result = simulate_regime(prices.index[0], prices.index[-1], prices, iv,
                             target_delta=0.50, budget_frac=0.001, capital=1_000)
    assert result is None


def test_simulate_regime_with_rolls_produces_multiple_legs_for_long_regime():
    # Regime longer than one roll window (TENOR_DAYS - ROLL_DTE) must roll
    # into a fresh leg rather than holding one contract to expiry.
    n = 400
    prices = pd.Series(
        [100 + i * 0.3 for i in range(n)],
        index=pd.bdate_range("2024-01-01", periods=n),
    )
    iv = _flat_iv(n, 20.0)
    sub_trades, agg = simulate_regime_with_rolls(
        prices.index[0], prices.index[-1], prices, iv,
        target_delta=0.50, budget_frac=0.05, capital=100_000)
    assert agg is not None
    roll_window_days = TENOR_DAYS - ROLL_DTE
    expected_min_legs = ((prices.index[-1] - prices.index[0]).days // roll_window_days)
    assert agg["n_legs"] >= max(1, expected_min_legs)


def test_simulate_regime_with_rolls_skips_legs_too_small_for_one_contract():
    # Same budget-floor fix as simulate_regime, but for the rolling multi-leg
    # path: a leg the budget can't afford must be skipped, not overspent.
    n = 200
    prices = _flat_prices(n, 500.0)
    iv = _flat_iv(n, 80.0)
    sub_trades, agg = simulate_regime_with_rolls(
        prices.index[0], prices.index[-1], prices, iv,
        target_delta=0.50, budget_frac=0.001, capital=1_000)
    assert sub_trades == []
    assert agg is None


def test_realized_vol_falls_back_when_too_little_history():
    prices = _flat_prices(3, 100.0)
    assert _realized_vol(prices, prices.index[-1]) == pytest.approx(0.20)


def test_realized_vol_is_zero_for_a_flat_price_series():
    prices = _flat_prices(30, 100.0)
    assert _realized_vol(prices, prices.index[-1]) == pytest.approx(0.0, abs=1e-9)
