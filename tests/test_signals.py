"""Signal generation: exact behavior on hand-constructed series."""

import numpy as np
import pandas as pd
import pytest

from signals import ma
from signals.combo import all_of, any_of, majority_of
from strategies import momentum


def _series(values, start="2024-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


class TestMACrossover:
    def test_uptrend_is_all_bullish_after_warmup(self):
        prices = _series(range(100, 160))
        sig = ma.signal(prices, fast=3, slow=10)
        assert (sig.iloc[10:] == 1).all()

    def test_downtrend_is_all_bearish(self):
        prices = _series(range(160, 100, -1))
        sig = ma.signal(prices, fast=3, slow=10)
        assert (sig == 0).all()

    def test_warmup_period_defaults_to_bearish(self):
        # NaN MAs compare False, so days before the slow window fills are 0
        prices = _series(range(100, 160))
        sig = ma.signal(prices, fast=3, slow=10)
        assert len(sig) == len(prices)
        assert (sig.iloc[:9] == 0).all()

    def test_v_shape_flips_bearish_then_bullish(self):
        prices = _series(list(range(200, 140, -1)) + list(range(140, 260, 2)))
        sig = ma.signal(prices, fast=5, slow=20)
        assert sig.iloc[25] == 0          # mid-decline
        assert sig.iloc[-1] == 1          # recovered
        flips = sig.diff().abs().sum()
        assert flips == 1                 # exactly one bear->bull flip, no whipsaw

    def test_values_are_binary_ints(self):
        prices = _series(np.linspace(100, 120, 50))
        sig = ma.signal(prices, fast=3, slow=10)
        assert set(sig.unique()) <= {0, 1}


class TestCombinators:
    a = pd.Series([1, 1, 0, 0], index=pd.bdate_range("2024-01-01", periods=4))
    b = pd.Series([1, 0, 1, 0], index=pd.bdate_range("2024-01-01", periods=4))
    c = pd.Series([1, 1, 1, 0], index=pd.bdate_range("2024-01-01", periods=4))

    def test_all_of(self):
        assert all_of([self.a, self.b, self.c]).tolist() == [1, 0, 0, 0]

    def test_any_of(self):
        assert any_of([self.a, self.b, self.c]).tolist() == [1, 1, 1, 0]

    def test_majority_of(self):
        assert majority_of([self.a, self.b, self.c]).tolist() == [1, 1, 1, 0]

    def test_alignment_uses_common_dates_only(self):
        short = self.b.iloc[1:]
        combined = all_of([self.a, short])
        assert len(combined) == 3
        assert combined.index[0] == self.a.index[1]


class TestMomentumPositions:
    def test_maps_signal_to_leverage(self):
        sig = pd.Series([0, 1, 1, 0], index=pd.bdate_range("2024-01-01", periods=4))
        pos = momentum.positions(sig, leverage=2.0)
        assert pos.tolist() == [1.0, 2.0, 2.0, 1.0]

    def test_cash_variant(self):
        sig = pd.Series([0, 1], index=pd.bdate_range("2024-01-01", periods=2))
        pos = momentum.positions(sig, leverage=2.0, no_signal_leverage=0.0)
        assert pos.tolist() == [0.0, 2.0]
