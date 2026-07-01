import pandas as pd


def _rsi(prices: pd.Series, period: int) -> pd.Series:
    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("inf"))
    return 100 - (100 / (1 + rs))


def signal(prices: pd.Series, period: int = 14, oversold: int = 30, overbought: int = 70) -> pd.Series:
    """
    Mean-reversion RSI band signal (stateful latch).
    Enters (1) when RSI falls below oversold; exits (0) when RSI rises above overbought.
    """
    rsi = _rsi(prices, period).dropna()
    state = 0
    result = []
    for val in rsi:
        if val < oversold:
            state = 1
        elif val > overbought:
            state = 0
        result.append(state)
    return pd.Series(result, index=rsi.index)
