"""
Momentum margin strategy.

When signal is bullish: hold at LEVERAGE x.
When signal is bearish: hold at 1x (no margin).
"""

import pandas as pd
from core.config import LEVERAGE


def positions(signal: pd.Series, leverage: float = LEVERAGE) -> pd.Series:
    """Convert a 0/1 signal into a leverage position series."""
    return signal.map({1: leverage, 0: 1.0})
