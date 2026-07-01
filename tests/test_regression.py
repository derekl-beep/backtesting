"""End-to-end golden test: signal -> positions -> simulator -> metrics.

Runs the full ETF pipeline on a fixed synthetic price series and asserts
exact outputs. If any refactor changes these numbers, live signals and every
backtest change with them — that must be a deliberate, reviewed decision.

Golden values frozen 2026-07-01 against the validated MA50/100-era engine.
"""

import numpy as np
import pandas as pd
import pytest

from core.metrics import calc
from core.simulator import run
from signals import ma
from strategies import momentum


@pytest.fixture(scope="module")
def pipeline_result():
    rng = np.random.default_rng(42)
    idx = pd.bdate_range("2020-01-01", periods=500)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, 500))), index=idx)

    sig = ma.signal(prices, 10, 30)
    pos = momentum.positions(sig)
    res = run(prices, pos, capital=10_000)
    return sig, res


def test_signal_flip_count_and_dates(pipeline_result):
    sig, _ = pipeline_result
    assert int(sig.diff().abs().sum()) == 23
    flips = sig[sig.diff() != 0].dropna()
    # first row is the initial state (diff is NaN there), real flips follow
    assert flips.index[1] == pd.Timestamp("2020-02-11")   # first bull flip
    assert flips.index[2] == pd.Timestamp("2020-04-15")   # first bear flip


def test_final_equity_and_fees(pipeline_result):
    _, res = pipeline_result
    assert res["equity"].iloc[-1] == pytest.approx(9747.264857, abs=1e-4)
    assert res["total_fees"] == pytest.approx(45.77, abs=1e-6)
    assert res["margin_calls"] == 0


def test_metrics(pipeline_result):
    _, res = pipeline_result
    m = calc(res["equity"])
    assert m["total"] == pytest.approx(-0.0252735143, abs=1e-8)
    assert m["cagr"] == pytest.approx(-0.0128442354, abs=1e-8)
    assert m["sharpe"] == pytest.approx(0.0671446068, abs=1e-8)
    assert m["max_dd"] == pytest.approx(-0.2719521981, abs=1e-8)
