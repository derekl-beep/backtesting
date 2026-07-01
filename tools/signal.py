"""
Live signal checker.

Shows current signal state, MA/RSI/MACD values, days in regime,
distance to flip, position sizing, and recent flip history.

Usage:
  python -m tools.signal SPMO
  python -m tools.signal SPMO GLD
  python -m tools.signal SPMO --capital 50000
"""

import sys
from datetime import date

import pandas as pd

from core.data import fetch
from core.config import LEVERAGE, INITIAL_CAPITAL, START
from signals import ma as sig_ma
from signals import rsi as sig_rsi
from signals import macd as sig_macd
from signals.combo import majority_of

# Per-ticker signal config — keep in sync with DEFAULT_PORTFOLIO in tools/portfolio.py
SIGNAL_CONFIGS = {
    "SPMO": dict(ma_fast=10, ma_slow=200),
    "GLD":  dict(ma_fast=20, ma_slow=100),
}
DEFAULT_CONFIG  = dict(ma_fast=50, ma_slow=100)
MACD_PARAMS     = (12, 26, 9)
FLIP_HISTORY    = 5


def _build_signal(prices, cfg):
    parts = [sig_ma.signal(prices, cfg["ma_fast"], cfg["ma_slow"])]
    if cfg.get("rsi"):
        parts.append(sig_rsi.signal(prices, threshold=cfg["rsi"]))
    if cfg.get("macd"):
        parts.append(sig_macd.signal(prices, *MACD_PARAMS))
    return parts[0] if len(parts) == 1 else majority_of(parts)


def _rsi_value(prices, period=14):
    delta = prices.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, float("inf"))
    return (100 - (100 / (1 + rs))).iloc[-1]


def _macd_values(prices, fast=12, slow=26, sig=9):
    ema_fast    = prices.ewm(span=fast, adjust=False).mean()
    ema_slow    = prices.ewm(span=slow, adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=sig, adjust=False).mean()
    return macd_line.iloc[-1], signal_line.iloc[-1]


def _find_flips(combined_signal, prices):
    flips = combined_signal.diff().abs()
    flip_dates = flips[flips == 1].index
    events = []
    for d in reversed(flip_dates):
        events.append({
            "date":      d,
            "direction": "BULL" if combined_signal.loc[d] == 1 else "BEAR",
            "price":     prices.loc[d],
        })
        if len(events) >= FLIP_HISTORY:
            break
    return events


def check(ticker: str, capital: float):
    cfg    = SIGNAL_CONFIGS.get(ticker, DEFAULT_CONFIG)
    prices = fetch(ticker, start=START)
    if len(prices) < cfg["ma_slow"] + 10:
        print(f"{ticker}: not enough data.")
        return

    combined = _build_signal(prices, cfg)
    bullish  = bool(combined.iloc[-1] == 1)

    ma_fast_s = prices.rolling(cfg["ma_fast"]).mean()
    ma_slow_s = prices.rolling(cfg["ma_slow"]).mean()

    today_price = prices.iloc[-1]
    today_fast  = ma_fast_s.iloc[-1]
    today_slow  = ma_slow_s.iloc[-1]
    ma_bullish  = today_fast > today_slow
    gap_pct     = (today_fast - today_slow) / today_slow * 100

    # Days in current regime
    regime_days = 0
    for val in reversed(combined.values[:-1]):
        if bool(val == 1) == bullish:
            regime_days += 1
        else:
            break

    was_bullish   = bool(combined.iloc[-2] == 1)
    just_flipped  = bullish != was_bullish

    # Signal label
    signals_used = [f"MA{cfg['ma_fast']}/{cfg['ma_slow']}"]
    if cfg.get("rsi"):
        signals_used.append(f"RSI>{cfg['rsi']}")
    if cfg.get("macd"):
        signals_used.append("MACD")
    sig_label = " + ".join(signals_used)
    vote_note  = " (majority)" if len(signals_used) > 1 else ""

    print(f"\n{'='*52}")
    print(f"  {ticker}  —  {date.today()}")
    print(f"  Strategy: {sig_label}{vote_note}")
    print(f"{'='*52}")
    print(f"  Price      : ${today_price:.2f}")
    print(f"  MA {cfg['ma_fast']:<3}     : ${today_fast:.2f}")
    print(f"  MA {cfg['ma_slow']:<3}     : ${today_slow:.2f}")
    ma_state = "✓ bull" if ma_bullish else "✗ bear"
    print(f"  MA gap     : {gap_pct:+.2f}%  ({ma_state})")

    if cfg.get("rsi"):
        rsi_val   = _rsi_value(prices)
        rsi_state = "✓ bull" if rsi_val > cfg["rsi"] else "✗ bear"
        print(f"  RSI(14)    : {rsi_val:.1f}  (>{cfg['rsi']} = {rsi_state})")

    if cfg.get("macd"):
        macd_val, macd_sig = _macd_values(prices, *MACD_PARAMS)
        macd_state = "✓ bull" if macd_val > macd_sig else "✗ bear"
        print(f"  MACD       : {macd_val:.3f}  signal {macd_sig:.3f}  ({macd_state})")

    print()
    if bullish:
        print(f"  SIGNAL  →  ✦ MARGIN ON  ({LEVERAGE:.0f}x)")
        if just_flipped:
            print(f"  *** FLIPPED BULLISH TODAY ***")
        else:
            print(f"  Bullish for {regime_days} trading days")
    else:
        print(f"  SIGNAL  →  ◦ MARGIN OFF  (1x)")
        if just_flipped:
            print(f"  *** FLIPPED BEARISH TODAY ***")
        else:
            print(f"  Bearish for {regime_days} trading days")

    # Distance to MA flip (MA is always the primary anchor)
    distance    = abs(today_fast - today_slow)
    direction   = "drop" if ma_bullish else "rise"
    pct_to_flip = distance / today_slow * 100
    print(f"\n  MA flip if MA{cfg['ma_fast']} needs to {direction} ~${distance:.2f} ({pct_to_flip:.1f}%)")

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
    flips = _find_flips(combined, prices)
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
