"""
Volatility-targeted continuous leverage: the strategy's scaling math, and the
walk-forward/significance harness in tools.vol_target. Key properties:
(1) leverage inside a bull regime moves opposite to realized vol and is
always clamped to [floor, cap]; (2) bear-regime days hold flat at
no_signal_leverage regardless of vol; (3) the significance test's null must
permute leverage values ONLY among bull days, preserving the exact average
leverage -- that's what makes it a fair "does the ordering matter" test
instead of a "does having less leverage matter" test.
"""

import numpy as np
import pandas as pd
import pytest

from strategies import vol_target
from strategies import momentum
from tools import vol_target as vt


def _bdate_series(values):
    idx = pd.bdate_range("2020-01-01", periods=len(values))
    return pd.Series(values, index=idx, dtype=float)


def test_realized_vol_zero_for_perfectly_flat_prices():
    prices = _bdate_series([100.0] * 60)
    vol = vol_target.realized_vol(prices, window=20).dropna()
    assert (vol == 0).all()


def test_positions_bear_regime_holds_at_no_signal_leverage():
    prices = _bdate_series(100 + np.cumsum(np.zeros(60)))
    signal = pd.Series(0, index=prices.index)
    pos = vol_target.positions(prices, signal, target_vol=0.2, window=10,
                                floor=1.0, cap=3.0, no_signal_leverage=1.0)
    assert (pos == 1.0).all()


def test_positions_zero_vol_bull_regime_caps_out():
    # perfectly flat price -> realized vol = 0 -> target/0 = inf -> clipped to cap
    prices = _bdate_series([100.0] * 60)
    signal = pd.Series(1, index=prices.index)
    pos = vol_target.positions(prices, signal, target_vol=0.2, window=10,
                                floor=1.0, cap=3.0)
    assert (pos == 3.0).all()


def test_positions_high_vol_bull_regime_floors_out():
    rng = np.random.default_rng(0)
    # deliberately huge daily moves -> realized vol far above target
    prices = _bdate_series(100 * np.exp(np.cumsum(rng.normal(0, 0.15, 80))))
    signal = pd.Series(1, index=prices.index)
    pos = vol_target.positions(prices, signal, target_vol=0.05, window=10,
                                floor=1.0, cap=3.0)
    assert (pos == 1.0).all()


def test_positions_never_breaches_floor_or_cap():
    rng = np.random.default_rng(1)
    prices = _bdate_series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, 300))))
    signal = pd.Series(rng.integers(0, 2, 300), index=prices.index)
    pos = vol_target.positions(prices, signal, target_vol=0.2, window=20,
                                floor=1.0, cap=2.5)
    assert (pos >= 1.0).all() and (pos <= 2.5).all()


def test_positions_scales_inversely_with_vol_within_bull_regime():
    # low-vol stretch then a high-vol stretch, both fully bull
    low_vol = 100 * np.exp(np.cumsum(np.full(60, 0.0005)))
    hi_rng = np.random.default_rng(2)
    high_vol = low_vol[-1] * np.exp(np.cumsum(hi_rng.normal(0, 0.05, 60)))
    prices = _bdate_series(np.concatenate([low_vol, high_vol]))
    signal = pd.Series(1, index=prices.index)
    pos = vol_target.positions(prices, signal, target_vol=0.15, window=20,
                                floor=1.0, cap=3.0)
    # window=20 warmup drops the first 20 days from `pos`'s index, so the
    # low-vol segment (original days 0-59) lands at pos positions 0-39 and
    # the high-vol segment (original days 60-119) at pos positions 40-99.
    avg_low = pos.iloc[20:40].mean()
    avg_high = pos.iloc[60:80].mean()
    assert avg_low > avg_high


# ---------------------------------------------------------------------------
# tools.vol_target harness
# ---------------------------------------------------------------------------

def test_run_params_returns_none_on_too_short_a_signal():
    prices = _bdate_series(np.linspace(100, 101, 10))
    ma_params = {"ma_fast": 10, "ma_slow": 200}
    vt_params = {"window": 20, "target_vol": 0.2, "floor": 1.0, "cap": 3.0}
    assert vt._run_params(prices, ma_params, vt_params) is None


def test_matched_baseline_uses_fixed_leverage_at_bull_days_and_1x_at_bear_days():
    rng = np.random.default_rng(3)
    prices = _bdate_series(100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, 300))))
    signal = pd.Series(rng.integers(0, 2, 300), index=prices.index)
    pos = momentum.positions(signal, leverage=1.7, no_signal_leverage=1.0)
    assert set(pos[signal == 1].unique()) == {1.7}
    assert set(pos[signal == 0].unique()) == {1.0}


def test_permute_bull_leverage_preserves_avg_and_bear_day_values():
    rng = np.random.default_rng(4)
    prices = _bdate_series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, 300))))
    signal = pd.Series(rng.integers(0, 2, 300), index=prices.index)
    pos = vol_target.positions(prices, signal, target_vol=0.2, window=20, cap=2.5)
    shuffled = vt._permute_bull_leverage(pos, signal, np.random.default_rng(5))

    sig_aligned = signal.reindex(pos.index)
    bear_days = sig_aligned == 0
    assert (shuffled[bear_days] == pos[bear_days]).all()
    assert shuffled.mean() == pytest.approx(pos.mean())
    assert sorted(shuffled[~bear_days].values) == pytest.approx(sorted(pos[~bear_days].values))


def test_walk_forward_runs_end_to_end_on_synthetic_data(monkeypatch):
    idx = pd.bdate_range("2016-01-01", periods=2500)
    rng = np.random.default_rng(6)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, len(idx)))),
                        index=idx)
    monkeypatch.setattr(vt, "fetch", lambda t: prices)
    monkeypatch.setattr(vt, "resolve_signal_params",
                         lambda t: {"ma_fast": 10, "ma_slow": 100})

    fold_records, appearances = vt.walk_forward("TEST")
    assert fold_records
    for f in fold_records:
        if f.get("skipped"):
            continue
        assert f["params"]["window"] in vt.WINDOW_GRID
        assert f["params"]["target_vol"] in vt.TARGET_VOL_GRID
        assert f["params"]["cap"] in vt.CAP_GRID
        assert f["params"]["floor"] in vt.FLOOR_GRID
        assert min(vt.FLOOR_GRID) <= f["avg_leverage"] <= max(vt.CAP_GRID)


def test_significance_test_bounds_and_shape(monkeypatch):
    idx = pd.bdate_range("2016-01-01", periods=1500)
    rng = np.random.default_rng(7)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, len(idx)))),
                        index=idx)
    monkeypatch.setattr(vt, "fetch", lambda t: prices)
    monkeypatch.setattr(vt, "resolve_signal_params",
                         lambda t: {"ma_fast": 10, "ma_slow": 100})

    result = vt.significance_test("TEST", n_shifts=25, seed=0)
    assert result is not None
    assert 0.0 <= result["p_cagr"] <= 1.0
    assert 0.0 <= result["p_sharpe"] <= 1.0
    assert len(result["random_cagrs"]) == 25
    assert min(vt.FLOOR_GRID) <= result["avg_leverage"] <= max(vt.CAP_GRID)
