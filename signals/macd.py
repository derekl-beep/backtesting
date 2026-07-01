import pandas as pd


def signal(prices: pd.Series, fast: int = 12, slow: int = 26, signal_period: int = 9) -> pd.Series:
    """MACD crossover: 1 when MACD line > signal line, else 0."""
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    return (macd_line > signal_line).astype(int).dropna()
