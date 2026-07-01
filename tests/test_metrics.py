"""Metrics: exact values on hand-computable equity curves."""

import pandas as pd
import pytest

from core.metrics import calc


def _equity(values):
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)), dtype=float)


def test_total_return():
    m = calc(_equity([100, 110, 121]))
    assert m["total"] == pytest.approx(0.21)


def test_cagr_annualizes_by_return_days():
    equity = _equity([100, 110, 121])
    n_years = 2 / 252
    assert calc(equity)["cagr"] == pytest.approx(1.21 ** (1 / n_years) - 1)


def test_max_drawdown():
    m = calc(_equity([100, 80, 120, 90]))
    assert m["max_dd"] == pytest.approx(-0.25)   # 120 -> 90 (peak-relative)
    m2 = calc(_equity([100, 80, 90]))
    assert m2["max_dd"] == pytest.approx(-0.20)  # 100 -> 80


def test_no_drawdown_is_zero():
    assert calc(_equity([100, 105, 110]))["max_dd"] == pytest.approx(0.0)


def test_constant_equity_has_zero_sharpe():
    assert calc(_equity([100, 100, 100]))["sharpe"] == 0.0
