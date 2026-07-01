"""
Live signal checker — MA50/100 crossover strategy.

Prints current margin ON/OFF status.

Usage:
  python -m tools.signal
  python -m tools.signal SPMO QQQ
"""

import sys
from datetime import date

from core.data import fetch
from core.config import LEVERAGE
from signals import ma as sig_ma

MA_FAST = 50
MA_SLOW = 100


def check(ticker: str):
    prices = fetch(ticker, period=f"{MA_SLOW * 2}d")
    if len(prices) < MA_SLOW:
        print(f"{ticker}: not enough data.")
        return

    ma_fast = prices.rolling(MA_FAST).mean()
    ma_slow = prices.rolling(MA_SLOW).mean()

    today_price = prices.iloc[-1]
    today_fast  = ma_fast.iloc[-1]
    today_slow  = ma_slow.iloc[-1]
    prev_fast   = ma_fast.iloc[-2]
    prev_slow   = ma_slow.iloc[-2]

    bullish     = today_fast > today_slow
    was_bullish = prev_fast > prev_slow
    gap_pct     = (today_fast - today_slow) / today_slow * 100
    distance    = today_fast - today_slow

    just_crossed_bullish = bullish and not was_bullish
    just_crossed_bearish = not bullish and was_bullish

    cross_days = 0
    for i in range(2, len(ma_fast)):
        if bullish:
            if ma_fast.iloc[-i] <= ma_slow.iloc[-i]:
                break
        else:
            if ma_fast.iloc[-i] >= ma_slow.iloc[-i]:
                break
        cross_days += 1

    print(f"\n{'='*50}")
    print(f"  {ticker}  —  {date.today()}")
    print(f"  Strategy: MA{MA_FAST}/{MA_SLOW} crossover")
    print(f"{'='*50}")
    print(f"  Price      : ${today_price:.2f}")
    print(f"  MA {MA_FAST:<3}      : ${today_fast:.2f}")
    print(f"  MA {MA_SLOW:<3}      : ${today_slow:.2f}")
    print(f"  MA gap     : {gap_pct:+.2f}%  ({'fast above slow' if bullish else 'fast below slow'})")
    print()

    if bullish:
        print(f"  SIGNAL  →  ✦ MARGIN ON  ({LEVERAGE}x)")
        if just_crossed_bullish:
            print(f"  *** CROSSED BULLISH TODAY — consider turning margin on ***")
        else:
            print(f"  Bullish for ~{cross_days} trading days")
    else:
        print(f"  SIGNAL  →  ◦ MARGIN OFF (1x, no margin)")
        if just_crossed_bearish:
            print(f"  *** CROSSED BEARISH TODAY — consider turning margin off ***")
        else:
            print(f"  Bearish for ~{cross_days} trading days")

    direction = "drop" if bullish else "rise"
    print(f"\n  Distance to cross: ${abs(distance):.2f} "
          f"(MA{MA_FAST} needs to {direction} to cross)")
    print()


if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["SPMO"]
    for t in tickers:
        check(t.upper())
