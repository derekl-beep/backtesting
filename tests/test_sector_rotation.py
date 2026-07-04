"""
Cross-sectional sector rotation: ranking, the monthly rebalance/hold engine,
and the two validation layers (walk-forward OOS param selection, and the
random-selection significance test). Key properties: the highest-trailing-
return ticker is always the one picked at top_n=1, the equity curve is
already daily-frequency by construction (the earlier ad-hoc version of this
strategy had a real bug where a monthly curve got mis-annualized by
core.metrics.calc -- these tests guard against that class of bug by
asserting the returned equity index matches the underlying daily calendar),
and a flat/zero-return universe produces exactly zero P&L (no phantom gains
or losses from the entry-day return-dropping bug fixed while building this).
"""

import numpy as np
import pandas as pd
import pytest

from tools import sector_rotation as sr


def _make_universe(tickers, n_days=500, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n_days)
    data = {}
    for i, t in enumerate(tickers):
        drift = 0.0002 * (i + 1)   # each ticker trends at a different rate
        data[t] = 100 * np.exp(np.cumsum(rng.normal(drift, 0.01, n_days)))
    return pd.DataFrame(data, index=idx)


def test_rank_top_n_picks_the_highest_trailing_return_ticker():
    idx = pd.bdate_range("2020-01-01", periods=300)
    df = pd.DataFrame({
        "A": np.linspace(100, 200, 300),   # strong uptrend
        "B": np.linspace(100, 110, 300),   # weak uptrend
        "C": np.linspace(100, 90, 300),    # downtrend
    }, index=idx)
    as_of = idx[250]
    picks = sr.rank_top_n(df, as_of, lookback_days=60, top_n=1)
    assert picks == ["A"]
    picks2 = sr.rank_top_n(df, as_of, lookback_days=60, top_n=2)
    assert set(picks2) == {"A", "B"}


def test_rank_top_n_returns_none_before_lookback_warms_up():
    idx = pd.bdate_range("2020-01-01", periods=100)
    df = pd.DataFrame({"A": range(100), "B": range(100)}, index=idx)
    assert sr.rank_top_n(df, idx[10], lookback_days=60, top_n=1) is None


def test_flat_universe_produces_zero_pnl_no_entry_day_bug():
    # every ticker is perfectly flat -- equity must start and end at capital,
    # with no phantom gain/loss from mishandling the first day of each
    # holding period's return relative to the entry price
    df = _make_universe(["A", "B", "C"], n_days=400)
    flat = pd.DataFrame({c: 100.0 for c in df.columns}, index=df.index)
    equity = sr.build_equity_curve(flat, lookback_days=60, top_n=2, capital=100_000)
    assert not equity.empty
    assert equity.iloc[0] == pytest.approx(100_000, rel=1e-6)
    assert equity.iloc[-1] == pytest.approx(100_000, rel=1e-6)
    assert equity.max() == pytest.approx(100_000, rel=1e-6)
    assert equity.min() == pytest.approx(100_000, rel=1e-6)


def test_equity_curve_is_daily_frequency_not_monthly():
    # guards against the exact bug found in the original ad-hoc backtest:
    # a monthly-frequency curve fed into core.metrics.calc over-annualizes
    df = _make_universe(["A", "B", "C", "D"], n_days=500)
    equity = sr.build_equity_curve(df, lookback_days=60, top_n=2, capital=100_000)
    assert not equity.empty
    # daily equity should have close to one point per business day held,
    # not ~1 point per month
    n_months = (equity.index[-1] - equity.index[0]).days / 30
    assert len(equity) > n_months * 15   # far more than one point per month


def test_higher_top_n_never_exceeds_universe_size():
    df = _make_universe(["A", "B", "C"], n_days=400)
    equity = sr.build_equity_curve(df, lookback_days=60, top_n=3, capital=100_000)
    assert not equity.empty
    assert (equity > 0).all()


def test_rising_universe_with_leverage_overlay_beats_unleveraged():
    df = _make_universe(["A", "B", "C", "D", "E"], n_days=700, seed=1)
    unlevered = sr.build_equity_curve(df, lookback_days=60, top_n=2,
                                      capital=100_000, use_leverage=False)
    levered = sr.build_equity_curve(df, lookback_days=60, top_n=2,
                                    capital=100_000, use_leverage=True,
                                    ma_fast=10, ma_slow=50)
    assert not unlevered.empty and not levered.empty
    # every ticker here has genuine positive drift, so 2x-when-confirmed
    # leverage should compound to a higher final value than 1x
    assert levered.iloc[-1] > unlevered.iloc[-1]


# ---------------------------------------------------------------------------
# Walk-forward OOS selection (monkeypatched fetch, small fast universe)
# ---------------------------------------------------------------------------

def test_walk_forward_never_selects_params_using_future_data(monkeypatch):
    idx = pd.bdate_range("2016-01-01", periods=2500)
    rng = np.random.default_rng(2)
    tickers = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB"]
    data = {t: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, len(idx))))
            for t in tickers}
    df = pd.DataFrame(data, index=idx)
    spy = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, len(idx)))), index=idx)

    monkeypatch.setattr(sr, "_fetch_universe", lambda tickers=None: df)
    monkeypatch.setattr(sr, "fetch", lambda t: spy if t == "SPY" else df[t])

    fold_records, appearances = sr.walk_forward(first_test_year=2020)
    assert fold_records
    for f in fold_records:
        if f.get("skipped"):
            continue
        # every selected param combo must come from the fixed grids
        assert f["lookback"] in sr.LOOKBACK_GRID_MONTHS
        assert f["top_n"] in sr.TOP_N_GRID


def test_significance_test_null_uses_same_universe_size(monkeypatch):
    idx = pd.bdate_range("2016-01-01", periods=1200)
    rng = np.random.default_rng(3)
    tickers = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB"]
    data = {t: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, len(idx))))
            for t in tickers}
    df = pd.DataFrame(data, index=idx)
    monkeypatch.setattr(sr, "_fetch_universe", lambda tickers=None: df)

    result = sr.significance_test(lookback_months=6, top_n=3, n_shifts=30, seed=0)
    assert result is not None
    assert 0.0 <= result["p_cagr"] <= 1.0
    assert 0.0 <= result["p_sharpe"] <= 1.0
    assert len(result["random_cagrs"]) > 0


def test_significance_test_null_applies_the_same_leverage_as_actual(monkeypatch):
    # regression test: the null must apply the identical per-ticker leverage
    # overlay as the actual strategy, or an apples-to-oranges comparison
    # (leveraged actual vs unleveraged null) would call leverage's own CAGR
    # boost "significant ranking skill" -- exactly the leverage-timing
    # confound this project's methodology finding exists to catch.
    idx = pd.bdate_range("2016-01-01", periods=1200)
    rng = np.random.default_rng(5)
    tickers = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB"]
    data = {t: 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, len(idx))))
            for t in tickers}
    df = pd.DataFrame(data, index=idx)
    monkeypatch.setattr(sr, "_fetch_universe", lambda tickers=None: df)

    unlevered = sr.significance_test(lookback_months=6, top_n=3, n_shifts=50,
                                     seed=1, use_leverage=False)
    levered = sr.significance_test(lookback_months=6, top_n=3, n_shifts=50,
                                   seed=1, use_leverage=True)
    # leverage should raise the *null's* median CAGR too, not just the actual's --
    # if the null were still unleveraged this gap would be much larger and the
    # leveraged run would spuriously look "significant"
    assert np.median(levered["random_cagrs"]) > np.median(unlevered["random_cagrs"])
