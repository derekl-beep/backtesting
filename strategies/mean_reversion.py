"""
Mean-reversion strategy.

When signal is ON (oversold, expect reversion up): hold at 1x.
When signal is OFF (overbought or neutral): go to cash (0x).

No leverage — mean-reversion captures snap-back moves, not sustained trends.
"""

import pandas as pd


def positions(signal: pd.Series) -> pd.Series:
    """1x when signal is ON, 0x (cash) when signal is OFF."""
    return signal.map({1: 1.0, 0: 0.0})
