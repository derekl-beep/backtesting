"""
signals/rsi.py's _rsi -- pins the fix for a real inverted-edge-case bug
found while building tools.mean_reversion: a lookback window with zero
losses (an uninterrupted uptrend) must produce RSI=100 (maximally
overbought), not RSI=0 (maximally oversold, the opposite reading). The old
code replaced a zero *loss* with infinity before dividing, which computes
gain/inf -> 0 -> RSI -> 0 -- backwards. A perfectly flat window (no gains,
no losses) is the separate, genuinely ambiguous case and reads as neutral (50).
"""

import numpy as np
import pandas as pd
import pytest

from signals.rsi import _rsi, signal


def test_uninterrupted_uptrend_is_maximally_overbought():
    prices = pd.Series([100.0 + i for i in range(30)])
    rsi = _rsi(prices, 14)
    assert rsi.iloc[-1] == pytest.approx(100.0)


def test_uninterrupted_downtrend_is_maximally_oversold():
    prices = pd.Series([100.0 - i for i in range(30)])
    rsi = _rsi(prices, 14)
    assert rsi.iloc[-1] == pytest.approx(0.0)


def test_perfectly_flat_window_is_neutral():
    prices = pd.Series([100.0] * 30)
    rsi = _rsi(prices, 14)
    assert rsi.iloc[-1] == pytest.approx(50.0)


def test_rsi_is_always_bounded_0_to_100():
    rng = np.random.default_rng(0)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 500))))
    rsi = _rsi(prices, 14).dropna()
    assert (rsi >= 0).all() and (rsi <= 100).all()


def test_mixed_up_and_down_days_matches_hand_computed_value():
    # 15 prices -> 14 deltas: alternating +2/-1, period=14 covers all of them
    prices = pd.Series([100, 102, 101, 103, 102, 104, 103, 105, 104, 106,
                       105, 107, 106, 108, 107])
    rsi = _rsi(prices, 14)
    # avg gain: seven +2 deltas -> 14/14=1.0; avg loss: seven -1 deltas -> 7/14=0.5
    # RS = 1.0/0.5 = 2.0 -> RSI = 100 - 100/3 = 66.67
    assert rsi.iloc[-1] == pytest.approx(66.667, abs=1e-2)


def test_signal_thresholds_the_fixed_rsi():
    prices = pd.Series([100.0 + i for i in range(30)])
    sig = signal(prices, period=14, threshold=50)
    assert sig.iloc[-1] == 1   # RSI=100 > 50 -> momentum-building signal is ON
