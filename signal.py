"""
Live signal checker for SPMO MA 50/100 momentum strategy.

Fetches recent price data, computes the current MA signal,
and tells you whether margin should be ON or OFF.

Usage:
  python signal.py          # checks SPMO
  python signal.py SPMO QQQ
"""

import sys
import yfinance as yf
import pandas as pd
from datetime import date

# Must match backtest.py config
MA_FAST = 50
MA_SLOW = 100
LEVERAGE = 2.0


def check_signal(ticker):
    # Fetch enough history to compute MA_SLOW
    raw = yf.download(ticker, period=f"{MA_SLOW * 2}d", auto_adjust=True, progress=False)
    prices = raw["Close"].squeeze().dropna()

    if len(prices) < MA_SLOW:
        print(f"{ticker}: not enough data.")
        return

    ma_fast = prices.rolling(MA_FAST).mean()
    ma_slow = prices.rolling(MA_SLOW).mean()

    today_price  = prices.iloc[-1]
    today_fast   = ma_fast.iloc[-1]
    today_slow   = ma_slow.iloc[-1]
    prev_fast    = ma_fast.iloc[-2]
    prev_slow    = ma_slow.iloc[-2]

    signal       = today_fast > today_slow
    prev_signal  = prev_fast > prev_slow
    gap_pct      = (today_fast - today_slow) / today_slow * 100
    distance_to_cross = today_fast - today_slow  # positive = bullish, negative = bearish

    # Detect crossover today
    just_crossed_bullish = signal and not prev_signal
    just_crossed_bearish = not signal and prev_signal

    print(f"\n{'='*50}")
    print(f"  {ticker}  —  {date.today()}")
    print(f"{'='*50}")
    print(f"  Price      : ${today_price:.2f}")
    print(f"  MA {MA_FAST:<3}      : ${today_fast:.2f}")
    print(f"  MA {MA_SLOW:<3}      : ${today_slow:.2f}")
    print(f"  MA gap     : {gap_pct:+.2f}%  ({'fast above slow' if signal else 'fast below slow'})")

    print()
    if signal:
        print(f"  SIGNAL     : ✦ MARGIN ON  ({LEVERAGE}x)")
        if just_crossed_bullish:
            print(f"  *** CROSSED BULLISH TODAY — consider turning margin on ***")
        else:
            # Estimate days since cross
            cross_days = 0
            for i in range(2, len(ma_fast)):
                if (ma_fast.iloc[-i] <= ma_slow.iloc[-i]):
                    break
                cross_days += 1
            print(f"  Bullish for: ~{cross_days} trading days")
    else:
        print(f"  SIGNAL     : ◦ MARGIN OFF (1x, no margin)")
        if just_crossed_bearish:
            print(f"  *** CROSSED BEARISH TODAY — consider turning margin off ***")
        else:
            cross_days = 0
            for i in range(2, len(ma_fast)):
                if (ma_fast.iloc[-i] >= ma_slow.iloc[-i]):
                    break
                cross_days += 1
            print(f"  Bearish for: ~{cross_days} trading days")

    # How close to a crossover?
    print()
    print(f"  Distance to cross: ${abs(distance_to_cross):.2f} "
          f"({'would need fast MA to drop' if signal else 'would need fast MA to rise'} to cross)")
    print()


if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["SPMO"]
    for t in tickers:
        check_signal(t.upper())
