import pandas as pd


def signal(prices: pd.Series, fast: int, slow: int) -> pd.Series:
    """MA crossover: 1 when fast MA > slow MA, else 0."""
    ma_fast = prices.rolling(fast).mean()
    ma_slow = prices.rolling(slow).mean()
    return (ma_fast > ma_slow).astype(int).dropna()
