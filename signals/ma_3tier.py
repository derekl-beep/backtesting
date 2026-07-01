import pandas as pd


def signal(prices: pd.Series, fast: int, mid: int, slow: int = 200) -> pd.Series:
    """
    Three-tier MA signal.
      2 — fully bullish:  fast > mid AND mid > slow  → 2x leverage
      1 — neutral:        fast < mid BUT mid > slow  → hold 1x
      0 — bearish:        mid < slow                 → cash
    """
    ma_fast = prices.rolling(fast).mean()
    ma_mid  = prices.rolling(mid).mean()
    ma_slow = prices.rolling(slow).mean()

    above_slow = (ma_mid  > ma_slow).astype(int)  # controls 0x vs 1x
    above_mid  = (ma_fast > ma_mid).astype(int)   # controls 1x vs 2x

    # 0 when below_slow, 1 when above_slow only, 2 when both
    return (above_slow + above_slow * above_mid).dropna()
