import pandas as pd


def _rsi(prices: pd.Series, period: int) -> pd.Series:
    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("inf"))
    return 100 - (100 / (1 + rs))


def signal(prices: pd.Series, period: int = 14, threshold: int = 50) -> pd.Series:
    """RSI threshold: 1 when RSI > threshold (momentum building), else 0."""
    rsi = _rsi(prices, period)
    return (rsi > threshold).astype(int).dropna()
