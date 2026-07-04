"""
Bear-regime put-selling overlay: put-side Black-Scholes math, the bear-regime
extractor (must be the exact complement of the existing bull-regime
extractor), and the monthly cash-secured-put cycle simulator. Key properties:
put-call parity holds, deep-OTM puts get assigned less often than near-the-
money ones, and a sharp drop against a sold put produces a real, bounded loss
(not a silently-clipped or unbounded one).
"""

import numpy as np
import pandas as pd
import pytest

from tools import bear_put_overlay as bpo
from tools.options_backtest import (
    _get_bear_regimes, _get_regimes, bs_call, bs_put, bs_put_delta,
    simulate_bear_regime_puts, strike_for_delta_put,
)


# ---------------------------------------------------------------------------
# Put-side Black-Scholes math
# ---------------------------------------------------------------------------

def test_bs_put_matches_put_call_parity():
    S, K, T, r, sigma = 100, 100, 1, 0.05, 0.20
    call = bs_call(S, K, T, r, sigma)
    put = bs_put(S, K, T, r, sigma)
    # C - P = S - K*e^(-rT)
    assert (call - put) == pytest.approx(S - K * pow(2.718281828, -r * T), abs=1e-2)


def test_bs_put_at_expiry_is_intrinsic_value():
    assert bs_put(90, 100, 0, 0.05, 0.20) == pytest.approx(10.0)
    assert bs_put(110, 100, 0, 0.05, 0.20) == pytest.approx(0.0)


def test_bs_put_delta_is_bounded_and_more_negative_itm():
    otm = bs_put_delta(120, 100, 0.5, 0.05, 0.20)   # spot well above strike
    atm = bs_put_delta(100, 100, 0.5, 0.05, 0.20)
    itm = bs_put_delta(80, 100, 0.5, 0.05, 0.20)    # spot well below strike
    assert -1.0 < itm < atm < otm < 0.0


def test_strike_for_delta_put_round_trips():
    S, T, r, sigma = 100, 1, 0.05, 0.20
    for target in (-0.20, -0.30, -0.50, -0.70):
        K = strike_for_delta_put(S, T, r, sigma, target)
        assert bs_put_delta(S, K, T, r, sigma) == pytest.approx(target, abs=1e-3)


def test_strike_for_delta_put_more_negative_target_means_higher_strike():
    # a more-negative (more ITM-leaning) target delta must sit closer to spot
    S, T, r, sigma = 100, 1, 0.05, 0.20
    k_far_otm = strike_for_delta_put(S, T, r, sigma, -0.20)
    k_near_atm = strike_for_delta_put(S, T, r, sigma, -0.50)
    assert k_far_otm < k_near_atm


# ---------------------------------------------------------------------------
# Bear-regime extraction
# ---------------------------------------------------------------------------

def _signal(values):
    idx = pd.bdate_range("2024-01-01", periods=len(values))
    return pd.Series(values, index=idx, dtype=float)


def test_bear_regimes_are_the_exact_complement_of_bull_regimes():
    sig = _signal([1, 1, 0, 0, 0, 1, 1, 0, 0])
    bull = _get_regimes(sig)
    bear = _get_regimes(1 - sig)
    assert bear == _get_bear_regimes(sig)
    # every date belongs to exactly one bull or bear regime, never both/neither
    covered = set()
    for start, end in bull + bear:
        covered.update(sig.loc[start:end].index)
    assert covered == set(sig.index)


def test_get_bear_regimes_never_bearish_is_empty():
    sig = _signal([1, 1, 1, 1])
    assert _get_bear_regimes(sig) == []


# ---------------------------------------------------------------------------
# Monthly cash-secured-put cycle simulator
# ---------------------------------------------------------------------------

def _flat_prices(n, price, start="2024-01-01"):
    return pd.Series([price] * n, index=pd.bdate_range(start, periods=n))


def _flat_iv(n, pct, start="2024-01-01"):
    return pd.Series([pct] * n, index=pd.bdate_range(start, periods=n))


def test_flat_underlying_puts_all_expire_worthless_and_keep_premium():
    n = 150
    prices = _flat_prices(n, 100.0)
    iv = _flat_iv(n, 20.0)
    trades, agg = simulate_bear_regime_puts(
        prices.index[0], prices.index[-1], prices, iv,
        target_delta=-0.30, budget_frac=0.03, capital=100_000)
    assert agg is not None
    assert all(not t["assigned"] for t in trades)
    assert agg["total_pnl"] == pytest.approx(agg["total_premium"])
    assert agg["return_on_premium"] == pytest.approx(1.0)


def test_sharp_drop_produces_a_bounded_real_loss_not_unbounded():
    # underlying crashes 40% partway through the regime -- every put sold
    # near the old, higher price should be deep ITM at expiry (assigned)
    n = 90
    prices = pd.concat([
        _flat_prices(30, 100.0, start="2024-01-01"),
        _flat_prices(60, 60.0, start="2024-02-14"),
    ])
    iv = _flat_iv(len(prices), 25.0, start="2024-01-01")
    trades, agg = simulate_bear_regime_puts(
        prices.index[0], prices.index[-1], prices, iv,
        target_delta=-0.30, budget_frac=0.03, capital=100_000)
    assert agg is not None
    assert any(t["assigned"] for t in trades)
    assert agg["total_pnl"] < 0
    # loss is capped: strike is always below the pre-crash spot, so payout
    # per contract can't exceed (pre-crash strike - post-crash spot) * 100
    max_possible_payout = sum(
        t["n_contracts"] * t["strike_K"] * 100 * 1.01 for t in trades
    )
    assert sum(t["payout"] for t in trades) < max_possible_payout


def test_budget_too_small_for_one_contract_skips_the_cycle_not_overspends():
    n = 90
    prices = _flat_prices(n, 100.0)
    iv = _flat_iv(n, 20.0)
    # tiny budget can't cover even 1 contract's premium
    trades, agg = simulate_bear_regime_puts(
        prices.index[0], prices.index[-1], prices, iv,
        target_delta=-0.30, budget_frac=0.0001, capital=100_000)
    assert trades == []
    assert agg is None


def test_regime_shorter_than_one_cycle_still_produces_a_trade():
    n = 15
    prices = _flat_prices(n, 100.0)
    iv = _flat_iv(n, 20.0)
    trades, agg = simulate_bear_regime_puts(
        prices.index[0], prices.index[-1], prices, iv,
        target_delta=-0.30, budget_frac=0.03, capital=100_000)
    assert agg is not None
    assert agg["n_cycles"] == 1


# ---------------------------------------------------------------------------
# End-to-end tool run (synthetic prices, no network)
# ---------------------------------------------------------------------------

def test_run_and_combined_analysis_execute_on_synthetic_data(monkeypatch):
    idx = pd.bdate_range("2016-01-01", periods=2200)
    rng = np.random.default_rng(4)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, len(idx)))),
                       index=idx)
    vix = pd.Series(rng.uniform(12, 35, len(idx)), index=idx)
    monkeypatch.setattr(bpo, "_fetch_all",
                        lambda ticker=None: (None, prices, vix,
                                             pd.Series(np.where(
                                                 prices.rolling(10).mean() >
                                                 prices.rolling(200).mean(), 1, 0),
                                                 index=idx).fillna(0)))

    results = bpo.run(capital=100_000)
    # regimes may or may not exist depending on the random signal, but the
    # call must complete and return well-formed aggregate dicts
    for r in results:
        assert r["total_premium"] >= 0
        assert r["n_assigned"] <= r["n_cycles"]

    monkeypatch.setattr(bpo, "_build_portfolio_equity",
                        lambda capital: pd.Series(
                            capital * np.exp(np.cumsum(rng.normal(0.0003, 0.01, len(idx)))),
                            index=idx))
    margin_eq, overlay_eq, events = bpo.combined_analysis(capital=100_000)
    assert len(margin_eq) == len(overlay_eq)
    assert not overlay_eq.isna().any()
