"""
VaR/CVaR math and the historical daily calculation. The property that
matters: CVaR must always be at least as severe as VaR (it's the average of
the tail beyond the VaR threshold, so it can never be a smaller loss), and
a known synthetic loss distribution must recover the correct percentile.
"""

import numpy as np
import pandas as pd
import pytest

from tools import tail_risk


def test_var_cvar_on_known_distribution():
    # 100 returns: -0.10, -0.09, ..., -0.01, 0.00, 0.01, ..., 0.89
    returns = np.arange(-10, 90) / 100.0
    var, cvar = tail_risk.var_cvar(returns, alpha=0.95)
    # 5% tail of 100 obs = 5 worst: -0.10..-0.06 (sorted ascending, idx=5 -> the 5th worst is -0.06)
    assert var == pytest.approx(0.06, abs=1e-9)
    assert cvar == pytest.approx(0.08, abs=1e-9)   # mean of -0.10..-0.06


def test_cvar_is_at_least_as_severe_as_var():
    rng = np.random.default_rng(0)
    returns = rng.normal(0.01, 0.05, 500)
    for alpha in (0.90, 0.95, 0.99):
        var, cvar = tail_risk.var_cvar(returns, alpha)
        assert cvar >= var


def test_negative_var_means_tail_outcome_is_still_a_gain():
    # every return positive -> even the "worst" tail outcome is a gain
    returns = np.linspace(0.01, 0.20, 200)
    var, cvar = tail_risk.var_cvar(returns, alpha=0.95)
    assert var < 0
    assert cvar < 0


def test_higher_alpha_is_a_more_extreme_tail():
    rng = np.random.default_rng(1)
    returns = rng.normal(0.0, 0.05, 1000)
    var_95, cvar_95 = tail_risk.var_cvar(returns, alpha=0.95)
    var_99, cvar_99 = tail_risk.var_cvar(returns, alpha=0.99)
    assert var_99 >= var_95
    assert cvar_99 >= cvar_95


def test_historical_daily_var_cvar_runs_on_synthetic_prices(monkeypatch):
    idx = pd.bdate_range("2016-01-01", periods=1500)
    rng = np.random.default_rng(2)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, len(idx)))), index=idx)
    monkeypatch.setattr(tail_risk, "fetch", lambda t: prices)
    monkeypatch.setattr(tail_risk, "resolve_signal_params",
                        lambda t: {"ma_fast": 10, "ma_slow": 50})

    (var, cvar), n_obs = tail_risk.historical_daily_var_cvar("TEST", alpha=0.95)
    assert n_obs > 1000
    assert cvar >= var
    assert var > -1 and var < 1   # sane daily-return-scale bounds, not garbage
