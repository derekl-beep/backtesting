"""
Combine multiple signal series into one.

Each signal is a pd.Series of 0/1 values. Signals are aligned by index
(inner join) before combining, so only dates present in all signals are used.
"""

import pandas as pd
from typing import List


def _align(signals: List[pd.Series]) -> pd.DataFrame:
    return pd.concat(signals, axis=1).dropna()


def all_of(signals: List[pd.Series]) -> pd.Series:
    """1 only when ALL signals agree (most conservative)."""
    df = _align(signals)
    return (df.sum(axis=1) == len(signals)).astype(int)


def any_of(signals: List[pd.Series]) -> pd.Series:
    """1 when ANY signal is 1 (most aggressive)."""
    df = _align(signals)
    return (df.sum(axis=1) >= 1).astype(int)


def majority_of(signals: List[pd.Series]) -> pd.Series:
    """1 when majority of signals are 1."""
    df = _align(signals)
    return (df.sum(axis=1) > len(signals) / 2).astype(int)
