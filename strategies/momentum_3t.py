"""
Three-tier momentum strategy.

Signal 2 → 2x leverage (fully bullish)
Signal 1 → 1x (neutral, hold)
Signal 0 → 0x cash (bearish)
"""

import pandas as pd
from core.config import LEVERAGE


def positions(signal: pd.Series, leverage: float = LEVERAGE) -> pd.Series:
    return signal.map({2: leverage, 1: 1.0, 0: 0.0})
