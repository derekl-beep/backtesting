"""
RSI-band mean-reversion signal, its 0x/1x-no-leverage position mapping, and
the walk-forward optimizer for the macro/EM tickers rejected under MA-
crossover momentum. Key property: the signal must *latch* (stay in-trade
after an oversold dip until RSI genuinely recovers past the overbought
band), not flip back out the moment RSI ticks up off the oversold line --
that hysteresis is the whole point of a band signal over a simple threshold.
"""

import numpy as np
import pandas as pd
import pytest

import signals.rsi_band as sig_rsi_band
from strategies import mean_reversion
from tools import mean_reversion as mr


def _prices_from_pattern(values):
    idx = pd.bdate_range("2020-01-01", periods=len(values))
    return pd.Series(values, index=idx, dtype=float)


def test_signal_enters_on_oversold_dip_and_latches_until_overbought():
    # a deep dip (RSI collapses) followed by a slow, partial recovery that
    # stays between the bands, then finally a strong rally through overbought
    n = 60
    prices = list(np.linspace(100, 100, 15))                 # flat warmup
    prices += list(np.linspace(100, 70, 10))                 # sharp drop -> oversold
    prices += list(np.linspace(70, 85, 15))                  # partial recovery, mid-band
    prices += list(np.linspace(85, 130, 20))                 # strong rally -> overbought
    prices = _prices_from_pattern(prices)

    sig = sig_rsi_band.signal(prices, period=14, oversold=30, overbought=70)
    assert sig.max() == 1
    # once entered, must remain 1 through the mid-band recovery (no premature exit)
    first_one = sig[sig == 1].index[0]
    mid_recovery_date = prices.index[35]
    if mid_recovery_date in sig.index and mid_recovery_date > first_one:
        assert sig.loc[mid_recovery_date] == 1
    # eventually exits once RSI clears the overbought band
    assert sig.iloc[-1] == 0


def test_signal_never_oversold_stays_flat():
    prices = _prices_from_pattern(np.linspace(100, 105, 60))   # gentle drift, no dip
    sig = sig_rsi_band.signal(prices, period=14, oversold=20, overbought=80)
    assert (sig == 0).all()


def test_signal_values_are_only_zero_or_one():
    rng = np.random.default_rng(0)
    prices = _prices_from_pattern(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 300))))
    sig = sig_rsi_band.signal(prices, period=14, oversold=30, overbought=70)
    assert set(sig.unique()) <= {0, 1}


def test_positions_maps_signal_to_1x_or_0x_no_leverage():
    sig = pd.Series([0, 1, 1, 0, 1], index=pd.bdate_range("2024-01-01", periods=5))
    pos = mean_reversion.positions(sig)
    assert list(pos) == [0.0, 1.0, 1.0, 0.0, 1.0]
    assert pos.max() <= 1.0   # never carries leverage


# ---------------------------------------------------------------------------
# Walk-forward optimizer
# ---------------------------------------------------------------------------

def test_run_params_returns_none_on_too_short_a_signal():
    prices = _prices_from_pattern(np.linspace(100, 101, 10))
    result = mr._run_params(prices, {"period": 14, "oversold": 30, "overbought": 70})
    assert result is None


def test_build_folds_respects_min_train_obs():
    idx = pd.bdate_range("2016-01-01", periods=400)
    prices = pd.Series(np.linspace(100, 110, 400), index=idx)
    folds = mr._build_folds(prices, first_test_year=2018, last_year=2018)
    # 400 business days from 2016-01-01 is under MIN_TRAIN_OBS by 2018 test year
    # for at least the earliest candidate fold -- either empty or well-formed
    for train, oos, test_year in folds:
        assert len(train) >= mr.MIN_TRAIN_OBS
        assert len(oos) >= 20


def test_walk_forward_runs_end_to_end_on_synthetic_data(monkeypatch):
    idx = pd.bdate_range("2016-01-01", periods=2500)
    rng = np.random.default_rng(1)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, len(idx)))),
                       index=idx)
    monkeypatch.setattr(mr, "fetch", lambda t: prices)

    fold_records, appearances = mr.walk_forward("TEST")
    assert fold_records
    for f in fold_records:
        if f.get("skipped"):
            continue
        assert f["params"]["oversold"] in mr.OVERSOLD_LEVELS
        assert f["params"]["overbought"] in mr.OVERBOUGHT_LEVELS


def test_significance_test_bounds_and_shape(monkeypatch):
    idx = pd.bdate_range("2016-01-01", periods=1500)
    rng = np.random.default_rng(2)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, len(idx)))),
                       index=idx)
    monkeypatch.setattr(mr, "fetch", lambda t: prices)

    result = mr.significance_test("TEST", n_shifts=25, seed=0)
    assert result is not None
    assert 0.0 <= result["p_cagr"] <= 1.0
    assert 0.0 <= result["p_sharpe"] <= 1.0
    assert len(result["random_cagrs"]) == 25
