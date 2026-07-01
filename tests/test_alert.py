"""Alert status for the daily watcher: flip and band-entry detection.

The cloud routine is stateless, so entered_band_today / flipped_today must be
derivable from history alone — these tests pin that logic.
"""

import numpy as np
import pandas as pd
import pytest

from tools.signal import alert_status

CFG = dict(ma_fast=3, ma_slow=10)
THRESHOLD = 2.0


def _series(values):
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)), dtype=float)


def _wiggly():
    # deterministic series whose MA3/MA10 gap repeatedly crosses the 2% band
    t = np.arange(200)
    return _series(100 + 8 * np.sin(t / 6) + 0.05 * t)


def _dist_pct(prices):
    ma_f = prices.rolling(CFG["ma_fast"]).mean()
    ma_s = prices.rolling(CFG["ma_slow"]).mean()
    return ((ma_f - ma_s).abs() / ma_s * 100).dropna()


def test_steady_uptrend_no_alert_conditions():
    prices = _series(np.linspace(100, 200, 120))
    s = alert_status("TEST", prices, CFG)
    assert s["signal"] == "ON"
    assert not s["flipped_today"]
    assert not s["entered_band_today"]
    assert s["days_in_regime"] > 50


def test_flip_today_detected():
    # long rise, then a one-day crash: MA3 crosses below MA10 on the last day
    prices = _series(list(np.linspace(100, 200, 60)) + [50])
    s = alert_status("TEST", prices, CFG)
    assert s["flipped_today"]
    assert s["signal"] == "OFF"


def test_entering_band_fires_once_then_stays_quiet():
    prices = _wiggly()
    dist = _dist_pct(prices)
    in_band = dist < THRESHOLD

    # find a day where the gap enters the band and stays in the next day
    entry_idx = None
    for i in range(1, len(in_band) - 1):
        if in_band.iloc[i] and not in_band.iloc[i - 1] and in_band.iloc[i + 1]:
            entry_idx = i
            break
    assert entry_idx is not None, "fixture never enters the band"

    entry_date = in_band.index[entry_idx]
    upto_entry = prices.loc[:entry_date]
    s = alert_status("TEST", upto_entry, CFG, threshold_pct=THRESHOLD)
    assert s["entered_band_today"]
    assert s["days_in_band"] == 1

    next_date = in_band.index[entry_idx + 1]
    upto_next = prices.loc[:next_date]
    s2 = alert_status("TEST", upto_next, CFG, threshold_pct=THRESHOLD)
    assert not s2["entered_band_today"]
    assert s2["days_in_band"] == 2


def test_reentry_after_leaving_band_fires_again():
    prices = _wiggly()
    dist = _dist_pct(prices)
    in_band = dist < THRESHOLD

    # find the second distinct entry into the band
    entries = [i for i in range(1, len(in_band))
               if in_band.iloc[i] and not in_band.iloc[i - 1]]
    assert len(entries) >= 2, "fixture must cross the band at least twice"

    second_entry_date = in_band.index[entries[1]]
    s = alert_status("TEST", prices.loc[:second_entry_date], CFG, threshold_pct=THRESHOLD)
    assert s["entered_band_today"]
    assert s["days_in_band"] == 1


def test_distances_match_independent_computation():
    prices = _wiggly()
    dist = _dist_pct(prices)
    s = alert_status("TEST", prices, CFG, threshold_pct=THRESHOLD)
    assert s["dist_to_flip_pct"] == pytest.approx(dist.iloc[-1], abs=0.01)
    assert s["dist_yesterday_pct"] == pytest.approx(dist.iloc[-2], abs=0.01)
