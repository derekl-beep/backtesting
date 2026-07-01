"""Market-close-aware price cache: freshness rules and network behavior."""

import os
from datetime import datetime, timedelta

import pandas as pd
import pytest

from core import data
from core.config import START


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "CACHE_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def no_network(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("network hit — cache should have served this")
    monkeypatch.setattr(data, "_download", _boom)


def _fake_prices(n=300):
    idx = pd.bdate_range(START, periods=n)
    return pd.Series(range(100, 100 + n), index=idx, name="TEST", dtype=float)


def test_last_market_close_is_recent_weekday_4pm():
    close = data._last_market_close()
    now = datetime.now(data._ET)
    assert close < now
    assert close.weekday() < 5
    assert (close.hour, close.minute) == (16, 0)
    assert now - close < timedelta(days=4)   # never further back than a long weekend


def test_fresh_cache_serves_without_network(cache_dir, no_network):
    prices = _fake_prices()
    prices.to_pickle(cache_dir / "TEST.pkl")   # just written -> after last close
    result = data.fetch("TEST")
    pd.testing.assert_series_equal(result, prices)


def test_stale_cache_triggers_refetch(cache_dir, monkeypatch):
    old = _fake_prices(100)
    path = cache_dir / "TEST.pkl"
    old.to_pickle(path)
    week_ago = (datetime.now() - timedelta(days=7)).timestamp()
    os.utime(path, (week_ago, week_ago))

    fresh = _fake_prices(200)
    monkeypatch.setattr(data, "_download", lambda *a, **k: fresh)
    result = data.fetch("TEST")
    assert len(result) == 200                      # refetched, not the stale 100
    assert len(pd.read_pickle(path)) == 200        # cache updated


def test_start_slicing_from_cache(cache_dir, no_network):
    prices = _fake_prices()
    prices.to_pickle(cache_dir / "TEST.pkl")
    later = str(prices.index[50].date())
    result = data.fetch("TEST", start=later)
    assert result.index[0] == prices.index[50]


def test_period_and_use_cache_false_bypass_cache(cache_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(data, "_download",
                        lambda *a, **k: calls.append(k) or _fake_prices())
    _fake_prices().to_pickle(cache_dir / "TEST.pkl")   # fresh cache present

    data.fetch("TEST", period="1y")
    data.fetch("TEST", use_cache=False)
    assert len(calls) == 2

    # and bypass calls must not overwrite the cache file's contents
    assert len(pd.read_pickle(cache_dir / "TEST.pkl")) == 300
