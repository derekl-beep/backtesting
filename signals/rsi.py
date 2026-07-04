import numpy as np
import pandas as pd


def _rsi(prices: pd.Series, period: int) -> pd.Series:
    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    # a window with zero losses means RS -> infinity -> RSI -> 100 (maximally
    # overbought). Replacing a zero *loss* with infinity (as this used to do)
    # computes the opposite: gain/inf -> 0 -> RSI -> 0 (maximally oversold) --
    # exactly backwards for an uninterrupted uptrend. Let the division produce
    # its natural inf/nan and handle the true zero-gain-and-zero-loss case
    # (a perfectly flat window) as neutral (50) instead.
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.mask((gain == 0) & (loss == 0), 50.0)


def signal(prices: pd.Series, period: int = 14, threshold: int = 50) -> pd.Series:
    """RSI threshold: 1 when RSI > threshold (momentum building), else 0."""
    rsi = _rsi(prices, period)
    return (rsi > threshold).astype(int).dropna()
