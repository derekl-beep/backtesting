"""
Monte Carlo forward simulation. Verifies calibration math, that both
simulation methods produce sane/bounded output on synthetic data (not just
"it runs"), and that a higher-volatility calibration produces a wider spread
of outcomes -- the property that actually matters for a risk tool.
"""

import numpy as np
import pandas as pd
import pytest

from tools import monte_carlo


def _price_series(n=1500, mu=0.0005, sigma=0.01, seed=0):
    idx = pd.bdate_range("2016-01-01", periods=n)
    rng = np.random.default_rng(seed)
    log_rets = rng.normal(mu, sigma, n)
    return pd.Series(100 * np.exp(np.cumsum(log_rets)), index=idx)


def test_calibrate_recovers_known_drift_and_vol():
    prices = _price_series(n=3000, mu=0.0006, sigma=0.011, seed=1)
    log_rets = np.log(prices / prices.shift(1)).dropna()
    mu, sigma = monte_carlo._calibrate(log_rets)
    assert mu == pytest.approx(0.0006, abs=0.0003)
    assert sigma == pytest.approx(0.011, abs=0.002)


def test_gbm_path_has_correct_length_and_moments():
    rng = np.random.default_rng(5)
    path = monte_carlo._gbm_path(0.0005, 0.01, 1000, rng)
    assert len(path) == 1000
    assert path.mean() == pytest.approx(0.0005, abs=0.002)
    assert path.std() == pytest.approx(0.01, abs=0.002)


def test_block_bootstrap_path_only_uses_observed_returns():
    rng = np.random.default_rng(6)
    log_rets = pd.Series(np.linspace(-0.01, 0.01, 500))
    path = monte_carlo._block_bootstrap_path(log_rets, 300, block_len=21, rng=rng)
    assert len(path) == 300
    # every value must come from the observed set (block resampling, not new draws)
    assert set(np.round(path, 8)).issubset(set(np.round(log_rets.values, 8)))


def test_forward_sim_runs_and_produces_bounded_output(monkeypatch):
    prices = _price_series(n=1500, mu=0.0004, sigma=0.01, seed=2)
    monkeypatch.setattr(monte_carlo, "fetch", lambda t: prices)
    monkeypatch.setattr(monte_carlo, "resolve_signal_params",
                        lambda t: {"ma_fast": 10, "ma_slow": 50})

    r = monte_carlo.forward_sim("TEST", horizon_years=1, n_sims=20, seed=3)
    for method in ("gbm", "block"):
        rows = r["results"][method]
        assert len(rows) == 20
        for row in rows:
            assert -1.0 < row["cagr"] < 20.0        # sane bounds, not NaN/inf
            assert -1.0 <= row["max_dd"] <= 0.0


def test_higher_volatility_widens_the_outcome_distribution(monkeypatch):
    """The core property a risk tool must have: more input vol -> wider
    spread of simulated outcomes, not a fixed/collapsed distribution."""
    calm_prices = _price_series(n=1500, mu=0.0004, sigma=0.005, seed=4)
    wild_prices = _price_series(n=1500, mu=0.0004, sigma=0.03, seed=4)

    monkeypatch.setattr(monte_carlo, "resolve_signal_params",
                        lambda t: {"ma_fast": 10, "ma_slow": 50})

    monkeypatch.setattr(monte_carlo, "fetch", lambda t: calm_prices)
    calm = monte_carlo.forward_sim("TEST", horizon_years=2, n_sims=100, seed=9)
    calm_cagrs = [row["cagr"] for row in calm["results"]["gbm"]]

    monkeypatch.setattr(monte_carlo, "fetch", lambda t: wild_prices)
    wild = monte_carlo.forward_sim("TEST", horizon_years=2, n_sims=100, seed=9)
    wild_cagrs = [row["cagr"] for row in wild["results"]["gbm"]]

    assert np.std(wild_cagrs) > np.std(calm_cagrs)
