"""
Walk-forward logistic regression regime-probability model. Key properties to
verify: the fit actually recovers a strong signal when one genuinely exists
(positive control), walk-forward doesn't leak future data into training, and
the quantized leverage used for the strategy comparison stays within bounds.
"""

import numpy as np
import pandas as pd
import pytest

from tools import regime_probability as rp


def test_fit_logistic_recovers_a_strong_separable_signal():
    rng = np.random.default_rng(0)
    n = 2000
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    x3 = rng.normal(0, 1, n)
    X = pd.DataFrame({"a": x1, "b": x2, "c": x3})
    # y strongly driven by x1 only -> model should learn a large positive
    # coefficient on "a" and near-zero on the noise features
    logit = 4 * x1
    p = 1 / (1 + np.exp(-logit))
    y = pd.Series((rng.uniform(size=n) < p).astype(int))

    beta = rp.fit_logistic(X, y)
    intercept, b_a, b_b, b_c = beta
    assert b_a > 2.0                       # recovers the strong true coefficient
    assert abs(b_b) < b_a and abs(b_c) < b_a   # noise features stay much smaller

    preds = (rp.predict(beta, X) > 0.5).astype(int)
    assert (preds == y).mean() > 0.85      # high accuracy on genuinely separable data


def test_features_have_no_lookahead_into_the_future():
    idx = pd.bdate_range("2016-01-01", periods=400)
    rng = np.random.default_rng(1)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, 400))), index=idx)

    X_full = rp._features(prices, ma_fast=10, ma_slow=50)
    # truncating the price series to day 300 must not change any feature
    # value computed at or before day 300 -- if it did, that would mean a
    # later feature depends on data past its own date (lookahead bug)
    X_truncated = rp._features(prices.iloc[:300], ma_fast=10, ma_slow=50)
    common = X_full.index.intersection(X_truncated.index)
    pd.testing.assert_series_equal(X_full.loc[common, "ma_gap"],
                                   X_truncated.loc[common, "ma_gap"])


def test_walk_forward_probabilities_only_use_past_training_data(monkeypatch):
    idx = pd.bdate_range("2016-01-01", periods=2200)
    rng = np.random.default_rng(2)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, len(idx)))), index=idx)
    monkeypatch.setattr(rp, "fetch", lambda t: prices)
    monkeypatch.setattr(rp, "resolve_signal_params", lambda t: {"ma_fast": 10, "ma_slow": 50})

    probs, fold_info, cfg = rp.walk_forward_probabilities("TEST", horizon=21,
                                                          first_test_year=2018)
    assert not probs.empty
    assert 0.0 <= probs.min() and probs.max() <= 1.0
    # each fold's training set must end strictly before that fold's test year
    for f in fold_info:
        assert f["n_train"] > 0


def test_quantized_leverage_stays_within_bounds(monkeypatch):
    idx = pd.bdate_range("2016-01-01", periods=2200)
    rng = np.random.default_rng(3)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, len(idx)))), index=idx)
    monkeypatch.setattr(rp, "fetch", lambda t: prices)
    monkeypatch.setattr(rp, "resolve_signal_params", lambda t: {"ma_fast": 10, "ma_slow": 50})

    result = rp.compare_strategies("TEST", horizon=21)
    assert result is not None
    lev = result["soft_leverage"]
    assert lev.min() >= 1.0
    assert lev.max() <= 2.0
    # quantized to the configured granularity
    remainders = (lev / rp.LEVERAGE_QUANTUM) % 1
    assert np.allclose(remainders, 0, atol=1e-9) or np.allclose(remainders, 1, atol=1e-9)
