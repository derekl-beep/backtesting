"""
Live signal checker — MA50/100 crossover strategy.

Usage:
  python -m tools.signal
  python -m tools.signal SPMO QQQ
  python -m tools.signal SPMO --capital 50000
"""

import sys
from datetime import date

import pandas as pd

from core.data import fetch
from core.config import LEVERAGE, INITIAL_CAPITAL, START

MA_FAST = 50
MA_SLOW = 100
FLIP_HISTORY = 5   # number of past signal flips to show


def _find_flips(ma_fast: pd.Series, ma_slow: pd.Series, prices: pd.Series) -> list[dict]:
    """Return list of crossover events, most recent first."""
    bull   = (ma_fast > ma_slow).dropna()
    signal = bull.astype(int)
    flips  = signal.diff().abs()
    flip_dates = flips[flips == 1].index

    events = []
    for d in reversed(flip_dates):
        events.append({
            "date":      d,
            "direction": "BULL" if bull.loc[d] else "BEAR",
            "price":     prices.loc[d],
        })
        if len(events) >= FLIP_HISTORY:
            break
    return events


def check(ticker: str, capital: float):
    prices = fetch(ticker, start=START)
    if len(prices) < MA_SLOW + 10:
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

    just_crossed_bullish = bullish and not was_bullish
    just_crossed_bearish = not bullish and was_bullish

    # Days in current regime
    bull_series = (ma_fast > ma_slow).dropna()
    regime_days = 0
    for val in reversed(bull_series.values[:-1]):
        if val == bullish:
            regime_days += 1
        else:
            break

    print(f"\n{'='*52}")
    print(f"  {ticker}  —  {date.today()}")
    print(f"  Strategy: MA{MA_FAST}/{MA_SLOW} crossover")
    print(f"{'='*52}")
    print(f"  Price   : ${today_price:.2f}")
    print(f"  MA {MA_FAST:<3}  : ${today_fast:.2f}")
    print(f"  MA {MA_SLOW:<3}  : ${today_slow:.2f}")
    print(f"  MA gap  : {gap_pct:+.2f}%  ({'fast > slow' if bullish else 'fast < slow'})")
    print()

    if bullish:
        print(f"  SIGNAL  →  ✦ MARGIN ON  ({LEVERAGE:.0f}x)")
        if just_crossed_bullish:
            print(f"  *** CROSSED BULLISH TODAY ***")
        else:
            print(f"  Bullish for {regime_days} trading days")
    else:
        print(f"  SIGNAL  →  ◦ MARGIN OFF  (1x)")
        if just_crossed_bearish:
            print(f"  *** CROSSED BEARISH TODAY ***")
        else:
            print(f"  Bearish for {regime_days} trading days")

    # How far to next flip
    distance   = abs(today_fast - today_slow)
    direction  = "drop" if bullish else "rise"
    pct_to_flip = distance / today_slow * 100
    print(f"\n  To flip signal: MA{MA_FAST} needs to {direction} ~${distance:.2f} "
          f"({pct_to_flip:.1f}% move)")

    # Position sizing
    print(f"\n  Position sizing  (capital: ${capital:,.0f})")
    print(f"  {'-'*40}")
    if bullish:
        total_value = capital * LEVERAGE
        shares      = total_value / today_price
        borrow      = capital * (LEVERAGE - 1)
        print(f"  Buy   : {shares:,.1f} shares  (${total_value:,.0f} total)")
        print(f"  Own   : ${capital:,.0f}  |  Borrow: ${borrow:,.0f}")
    else:
        shares = capital / today_price
        print(f"  Buy   : {shares:,.1f} shares  (${capital:,.0f}, no margin)")

    # Flip history
    flips = _find_flips(ma_fast, ma_slow, prices)
    if flips:
        print(f"\n  Last {len(flips)} signal flips:")
        print(f"  {'Date':<12} {'Direction':<8} {'Price':>8}")
        print(f"  {'-'*12} {'-'*8} {'-'*8}")
        for f in flips:
            arrow = "↑ BULL" if f["direction"] == "BULL" else "↓ BEAR"
            print(f"  {str(f['date'].date()):<12} {arrow:<8} ${f['price']:>7.2f}")
    print()


if __name__ == "__main__":
    args    = sys.argv[1:]
    capital = INITIAL_CAPITAL
    if "--capital" in args:
        idx     = args.index("--capital")
        capital = float(args[idx + 1])
        args    = [a for i, a in enumerate(args) if i != idx and i != idx + 1]

    tickers = args if args else ["SPMO"]
    for t in tickers:
        check(t.upper(), capital)
