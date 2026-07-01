"""
Live signal checker — MA30/50 + RSI>55 + MACD majority strategy.

Prints current margin ON/OFF status with reasoning from each signal component.

Usage:
  python -m tools.signal
  python -m tools.signal SPMO QQQ
"""

import sys
from datetime import date
import pandas as pd

from core.data import fetch
from core.config import LEVERAGE
import signals.ma   as sig_ma
import signals.rsi  as sig_rsi
import signals.macd as sig_macd

MA_FAST        = 30
MA_SLOW        = 50
RSI_PERIOD     = 14
RSI_THRESHOLD  = 55
MACD_FAST      = 12
MACD_SLOW      = 26
MACD_SIGNAL    = 9


def _rsi(prices, period):
    delta = prices.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, float("inf"))
    return 100 - (100 / (1 + rs))


def check(ticker: str):
    prices = fetch(ticker, period="300d")
    if len(prices) < MA_SLOW + MACD_SLOW + 10:
        print(f"{ticker}: not enough data.")
        return

    # MA
    ma_fast_s = prices.rolling(MA_FAST).mean()
    ma_slow_s = prices.rolling(MA_SLOW).mean()
    ma_bull   = ma_fast_s.iloc[-1] > ma_slow_s.iloc[-1]
    ma_gap    = (ma_fast_s.iloc[-1] - ma_slow_s.iloc[-1]) / ma_slow_s.iloc[-1] * 100

    # RSI
    rsi_s     = _rsi(prices, RSI_PERIOD)
    rsi_val   = rsi_s.iloc[-1]
    rsi_bull  = rsi_val > RSI_THRESHOLD

    # MACD
    ema_fast  = prices.ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow  = prices.ewm(span=MACD_SLOW, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    sig_line  = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
    macd_bull = macd_line.iloc[-1] > sig_line.iloc[-1]

    # Majority vote
    votes     = sum([ma_bull, rsi_bull, macd_bull])
    signal_on = votes >= 2

    # Days since last signal change
    all_signals = pd.DataFrame({
        "ma":   (ma_fast_s > ma_slow_s),
        "rsi":  (rsi_s > RSI_THRESHOLD),
        "macd": (macd_line > sig_line),
    }).dropna()
    majority = (all_signals.sum(axis=1) >= 2)
    cross_days = 0
    for i in range(2, len(majority)):
        if majority.iloc[-i] == signal_on:
            cross_days += 1
        else:
            break

    print(f"\n{'='*52}")
    print(f"  {ticker}  —  {date.today()}")
    print(f"  Strategy: MA{MA_FAST}/{MA_SLOW} + RSI>{RSI_THRESHOLD} + MACD majority")
    print(f"{'='*52}")
    print(f"  Price        : ${prices.iloc[-1]:.2f}")
    print()
    print(f"  MA {MA_FAST}/{MA_SLOW}      : {'✓ BULL' if ma_bull else '✗ BEAR'}  "
          f"(gap {ma_gap:+.2f}%)")
    print(f"  RSI ({RSI_PERIOD}d) >{RSI_THRESHOLD}  : {'✓ BULL' if rsi_bull else '✗ BEAR'}  "
          f"(RSI = {rsi_val:.1f})")
    print(f"  MACD         : {'✓ BULL' if macd_bull else '✗ BEAR'}  "
          f"(line {'above' if macd_bull else 'below'} signal)")
    print(f"\n  Vote         : {votes}/3 bullish")
    print()

    if signal_on:
        print(f"  SIGNAL  →  ✦ MARGIN ON  ({LEVERAGE}x)")
        print(f"  Active for ~{cross_days} trading days")
    else:
        print(f"  SIGNAL  →  ◦ MARGIN OFF (1x, no margin)")
        print(f"  Inactive for ~{cross_days} trading days")
        if votes == 1:
            print(f"  1 signal still bullish — watch for reversal")

    print()


if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["SPMO"]
    for t in tickers:
        check(t.upper())
