"""
RSI-band mean-reversion strategy.

When the signal is in-trade (oversold dip, not yet recovered): hold at 1x.
When flat: hold 0x (cash). Deliberately no persistent 2x leverage -- unlike
the momentum strategy, mean-reversion entries are lower-conviction, shorter-
duration counter-trend trades on tickers that don't trend cleanly enough for
an MA crossover (see research/etf_candidates.md), so this family doesn't
carry margin at all.
"""

import pandas as pd


def positions(signal: pd.Series) -> pd.Series:
    return signal.map({1: 1.0, 0: 0.0})
