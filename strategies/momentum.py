"""
Momentum margin strategy.

When signal is bullish: hold at LEVERAGE x.
When signal is bearish: hold at 1x (no margin).
"""

import pandas as pd
from core.config import LEVERAGE


def positions(signal: pd.Series, leverage: float = LEVERAGE,
              no_signal_leverage: float = 1.0) -> pd.Series:
    """
    Convert a 0/1 signal into a leverage position series.
    no_signal_leverage: 1.0 = hold 1x, 0.0 = go to cash
    """
    return signal.map({1: leverage, 0: no_signal_leverage})
