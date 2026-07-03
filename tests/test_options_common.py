"""
Shared overlay-input resolution (tools/options_common.py). All network access
is mocked -- these test the dispatch logic (known IV proxy vs realized-vol
fallback, cross-ticker SPMO->QQQ overlay vs a ticker's own signal->own calls),
not real market data.
"""

import numpy as np
import pandas as pd
import pytest

from tools import options_common
from tools.options_backtest import SIGNAL_TICKER, CALL_TICKER, IV_TICKER


def _series(name, n=60, start_value=100.0):
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.Series(start_value + np.arange(n), index=idx, name=name, dtype=float)


@pytest.fixture
def no_network(monkeypatch):
    def _boom(ticker, *a, **k):
        raise AssertionError(f"network hit for {ticker} -- should have been mocked")
    monkeypatch.setattr(options_common, "fetch", _boom)


def test_iv_proxy_series_uses_known_proxy_ticker(monkeypatch):
    vix_series = _series("^VIX", start_value=20.0)
    fetched = []

    def fake_fetch(ticker, *a, **k):
        fetched.append(ticker)
        return vix_series

    monkeypatch.setattr(options_common, "fetch", fake_fetch)
    result = options_common.iv_proxy_series("QQQ", _series("QQQ"))
    assert fetched == ["^VIX"]
    pd.testing.assert_series_equal(result, vix_series)


def test_iv_proxy_series_falls_back_to_realized_vol(no_network):
    prices = _series("XYZ_UNKNOWN_TICKER")
    result = options_common.iv_proxy_series("XYZ_UNKNOWN_TICKER", prices)
    assert list(result.index) == list(prices.index)
    assert result.notna().all()
    assert (result >= 0).all()


def test_overlay_inputs_for_signal_ticker_uses_cross_ticker_call_and_iv(monkeypatch):
    signal_prices = _series(SIGNAL_TICKER, start_value=50.0)
    call_prices   = _series(CALL_TICKER, start_value=400.0)
    iv_prices     = _series(IV_TICKER, start_value=20.0)

    def fake_fetch(ticker, *a, **k):
        return {SIGNAL_TICKER: signal_prices, CALL_TICKER: call_prices,
                IV_TICKER: iv_prices}[ticker]
    monkeypatch.setattr(options_common, "fetch", fake_fetch)

    call_out, iv_out, regimes, label = options_common.overlay_inputs(SIGNAL_TICKER)
    pd.testing.assert_series_equal(call_out, call_prices)
    pd.testing.assert_series_equal(iv_out, iv_prices)
    assert label == f"{SIGNAL_TICKER}→{CALL_TICKER}"


def test_overlay_inputs_for_other_ticker_uses_own_signal_and_calls(monkeypatch):
    ticker = "ZZZZ_NOT_A_REAL_TICKER"
    own_prices = _series(ticker, n=300, start_value=100.0)   # long enough for DEFAULT_SIGNAL MA100
    monkeypatch.setattr(options_common, "fetch", lambda t, *a, **k: own_prices)

    call_out, iv_out, regimes, label = options_common.overlay_inputs(ticker)
    pd.testing.assert_series_equal(call_out, own_prices)
    assert label == f"{ticker}→{ticker}"
    assert list(iv_out.index) == list(own_prices.index)   # realized-vol proxy, own price index
