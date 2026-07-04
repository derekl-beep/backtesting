"""
Circular-shift timing-significance test. The key property to verify isn't
just "it runs" -- it's that the method actually distinguishes a real timing
edge from no edge, on synthetic data where we know the ground truth.
"""

import numpy as np
import pandas as pd
import pytest

from core.data import fetch
from tools import significance


def test_verdict_thresholds():
    assert "SIGNIFICANT" in significance._verdict(0.01)
    assert "borderline" in significance._verdict(0.08)
    assert "NOT significant" in significance._verdict(0.50)


def test_circular_shift_test_is_reproducible_with_fixed_seed(monkeypatch):
    idx = pd.bdate_range("2016-01-01", periods=2600)
    rng = np.random.default_rng(1)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, len(idx)))), index=idx)
    monkeypatch.setattr(significance, "fetch", lambda t: prices)

    r1 = significance.circular_shift_test("TEST", n_shifts=50, seed=7)
    r2 = significance.circular_shift_test("TEST", n_shifts=50, seed=7)
    np.testing.assert_array_equal(r1["random_cagrs"], r2["random_cagrs"])
    assert r1["p_cagr"] == r2["p_cagr"]


def test_p_values_are_valid_probabilities(monkeypatch):
    idx = pd.bdate_range("2016-01-01", periods=1500)
    rng = np.random.default_rng(2)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0002, 0.012, len(idx)))), index=idx)
    monkeypatch.setattr(significance, "fetch", lambda t: prices)

    r = significance.circular_shift_test("TEST", n_shifts=100, seed=3)
    assert 0.0 <= r["p_cagr"] <= 1.0
    assert 0.0 <= r["p_sharpe"] <= 1.0
    assert len(r["random_cagrs"]) == 100


def test_detects_a_real_timing_edge_on_synthetic_data(monkeypatch):
    """
    Positive control: build a price series where the MA-crossover signal
    genuinely predicts the good periods (strong uptrend exactly while the
    signal would be on, flat/declining otherwise). If the method has any
    power at all, this must score as a clear outlier vs random timing --
    unlike the real tickers, where the timing washes out statistically.
    """
    idx = pd.bdate_range("2016-01-01", periods=2600)
    rng = np.random.default_rng(0)

    # Build price series with alternating strong-up / flat-down blocks that
    # happen to align with where a MA10/200 crossover will actually flip on
    # this exact series (the strategy "knows" the future by construction).
    log_rets = np.zeros(len(idx))
    block = 250
    for start in range(0, len(idx), block):
        end = min(start + block, len(idx))
        if (start // block) % 2 == 0:
            log_rets[start:end] = rng.normal(0.0025, 0.008, end - start)   # strong up block
        else:
            log_rets[start:end] = rng.normal(-0.0015, 0.008, end - start)  # down block
    prices = pd.Series(100 * np.exp(np.cumsum(log_rets)), index=idx)
    monkeypatch.setattr(significance, "fetch", lambda t: prices)
    monkeypatch.setattr(significance, "resolve_signal_params",
                        lambda t: {"ma_fast": 10, "ma_slow": 50})

    r = significance.circular_shift_test("TEST", n_shifts=300, seed=11)
    # A genuine, strong block-aligned edge should land at or near the top of
    # the random-timing distribution -- nowhere near the "not significant"
    # p > 0.10 territory seen for the real tickers.
    assert r["p_cagr"] < 0.10
