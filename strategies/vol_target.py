"""
Volatility-targeted continuous leverage.

Within a confirmed-bull regime (signal == 1), scale leverage continuously
against trailing realized volatility instead of holding a fixed multiple:
target_leverage = clip(target_vol / realized_vol, floor, cap). In a bear
regime, hold at no_signal_leverage (1x, same as strategies.momentum) --
the trend gate itself is unchanged, only the in-regime leverage differs.

core/simulator.py::run already treats `positions` as continuous target
leverage per day, so no simulator changes are needed to run this.
"""

import pandas as pd


def realized_vol(prices: pd.Series, window: int) -> pd.Series:
    """Trailing annualized realized volatility (rolling stdev of daily returns)."""
    return prices.pct_change().rolling(window).std() * (252 ** 0.5)


def positions(prices: pd.Series, signal: pd.Series, target_vol: float,
              window: int = 20, floor: float = 1.0, cap: float = 3.0,
              no_signal_leverage: float = 1.0) -> pd.Series:
    """
    Continuous leverage scaling within a confirmed-bull regime.

    signal: 0/1 regime series (e.g. from signals.ma), same convention as
    strategies.momentum. Bear-regime days hold at no_signal_leverage; a
    realized-vol reading of 0 (or a warmup NaN) is treated as "cap out",
    not as infinite leverage.
    """
    vol = realized_vol(prices, window)
    idx = signal.index.intersection(vol.index)
    vol = vol.reindex(idx)
    sig = signal.reindex(idx)

    scaled = (target_vol / vol).clip(lower=floor, upper=cap)
    leverage = scaled.where(sig == 1, no_signal_leverage)
    return leverage.dropna()
