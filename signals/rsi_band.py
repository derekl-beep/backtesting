import pandas as pd

from .rsi import _rsi


def signal(prices: pd.Series, period: int = 14, oversold: int = 30,
          overbought: int = 70) -> pd.Series:
    """
    Stateful RSI-band mean-reversion signal: enter (1) once RSI drops below
    `oversold`, stay in until RSI rises above `overbought`, then exit (0)
    until the next oversold dip. Unlike signals.rsi's simple threshold
    (flips every time RSI crosses one level, so it can flap right at the
    boundary), this latches between the two bands -- the same mechanism
    Roadmap describes for a contrarian ETF strategy.
    """
    rsi = _rsi(prices, period).dropna()
    state = 0
    out = []
    for val in rsi:
        if state == 0 and val < oversold:
            state = 1
        elif state == 1 and val > overbought:
            state = 0
        out.append(state)
    return pd.Series(out, index=rsi.index)
