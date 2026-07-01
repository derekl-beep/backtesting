"""
Momentum ranking tool.

Scans a watchlist and ranks stocks by current momentum strength.
Use this daily to identify entry candidates, then run stock_signal.py
for position sizing on the stocks that surface to the top.

Ranking uses a consistent MA50/100 signal across all tickers for fair
comparison. Per-stock strategy configs (in stock_signal.py) are for
execution, not ranking.

Strength score factors:
  - Signal tier (bullish vs bearish)
  - Days in current regime (longer = more confirmed)
  - MA gap % (larger = stronger trend)
  - RSI momentum (50–70 sweet spot: trending but not overbought)

Usage:
  python -m tools.stock_rank                              # default watchlist
  python -m tools.stock_rank NVDA MSFT AAPL TSLA META
  python -m tools.stock_rank --ma 20:50                  # custom MA params
"""

import sys
from datetime import date

import pandas as pd

from core.data import fetch
from core.config import START

MA_FAST = 50
MA_SLOW = 100

DEFAULT_WATCHLIST = [
    # Mega-cap tech
    "NVDA", "MSFT", "AAPL", "META", "GOOG", "AMZN",
    # Semiconductors
    "AMD", "AVGO", "TSM",
    # Consumer / other
    "TSLA", "COST", "V",
    # Finance
    "JPM", "GS",
    # Healthcare
    "LLY", "UNH",
    # Energy
    "XOM",
]


def _rsi(prices: pd.Series, period: int = 14) -> float:
    delta = prices.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, float("inf"))
    return float((100 - (100 / (1 + rs))).iloc[-1])


def _regime_days(sig: pd.Series, current: int) -> int:
    count = 0
    for val in reversed(sig.values[:-1]):
        if int(val) == current:
            count += 1
        else:
            break
    return count


def _strength_score(bullish: bool, days: int, gap_pct: float, rsi: float) -> float:
    """
    Composite 0–100 score for bullish stocks.
    Bearish stocks always score 0.
    """
    if not bullish:
        return 0.0
    # Regime duration: up to 30 pts (capped at 60 days)
    days_score = min(days / 60 * 30, 30)
    # MA gap: up to 40 pts (10% gap = full score)
    gap_score  = min(gap_pct / 10 * 40, 40) if gap_pct > 0 else 0
    # RSI sweet spot 55–70: up to 30 pts (RSI > 70 = overbought, penalise)
    if rsi > 70:
        rsi_score = max(30 - (rsi - 70) * 3, 0)
    elif rsi >= 50:
        rsi_score = (rsi - 50) / 20 * 30
    else:
        rsi_score = 0
    return days_score + gap_score + rsi_score


def _stars(score: float, bullish: bool) -> str:
    if not bullish:
        return "—"
    if score >= 60:
        return "★★★"
    if score >= 35:
        return "★★"
    return "★"


def _scan(ticker: str, ma_fast: int, ma_slow: int) -> dict | None:
    try:
        prices = fetch(ticker, start=START)
    except Exception:
        print(f"  {ticker}: failed to fetch")
        return None
    if len(prices) < ma_slow + 10:
        print(f"  {ticker}: not enough data")
        return None

    from signals import ma as sig_ma
    sig     = sig_ma.signal(prices, ma_fast, ma_slow)
    current = int(sig.iloc[-1])
    bullish = current == 1

    ma_fast_v  = float(prices.rolling(ma_fast).mean().iloc[-1])
    ma_slow_v  = float(prices.rolling(ma_slow).mean().iloc[-1])
    price      = float(prices.iloc[-1])
    gap_pct    = (ma_fast_v - ma_slow_v) / ma_slow_v * 100
    rsi_val    = _rsi(prices)
    days       = _regime_days(sig, current)
    score      = _strength_score(bullish, days, gap_pct, rsi_val)
    stars      = _stars(score, bullish)

    # Detect flip today
    just_flipped = int(sig.iloc[-1]) != int(sig.iloc[-2])

    return {
        "ticker":        ticker,
        "bullish":       bullish,
        "days":          days,
        "gap_pct":       gap_pct,
        "rsi":           rsi_val,
        "score":         score,
        "stars":         stars,
        "price":         price,
        "ma_fast":       ma_fast_v,
        "ma_slow":       ma_slow_v,
        "just_flipped":  just_flipped,
    }


def _print_table(rows: list[dict], ma_fast: int, ma_slow: int):
    bullish_rows = [r for r in rows if r["bullish"]]
    bearish_rows = [r for r in rows if not r["bullish"]]

    # Sort bullish by score desc, then bearish by gap_pct desc (least negative first)
    bullish_rows.sort(key=lambda r: r["score"], reverse=True)
    bearish_rows.sort(key=lambda r: r["gap_pct"], reverse=True)

    print(f"\n{'='*78}")
    print(f"  Momentum Ranking  —  {date.today()}  "
          f"(MA{ma_fast}/{ma_slow} signal, consistent across all tickers)")
    print(f"{'='*78}")
    print(f"  {'#':<4} {'Ticker':<8} {'Signal':<14} {'Days':>5} "
          f"{'MA gap':>8} {'RSI':>6} {'Score':>6} {'Strength':>9}")
    print(f"  {'-'*4} {'-'*8} {'-'*14} {'-'*5} "
          f"{'-'*8} {'-'*6} {'-'*6} {'-'*9}")

    rank = 1
    for r in bullish_rows:
        flip_tag = " ← NEW" if r["just_flipped"] else ""
        signal   = f"bull (2x){flip_tag}"
        print(f"  {rank:<4} {r['ticker']:<8} {signal:<14} {r['days']:>5} "
              f"  {r['gap_pct']:>+6.1f}% {r['rsi']:>6.1f} {r['score']:>6.0f} "
              f"{r['stars']:>9}")
        rank += 1

    if bearish_rows:
        print(f"  {'—'*4} {'—'*8} {'—'*14} {'—'*5} {'—'*8} {'—'*6} {'—'*6} {'—'*9}")
        for r in bearish_rows:
            flip_tag = " ← NEW" if r["just_flipped"] else ""
            signal   = f"bear (1x){flip_tag}"
            print(f"  {'—':<4} {r['ticker']:<8} {signal:<14} {r['days']:>5} "
                  f"  {r['gap_pct']:>+6.1f}% {r['rsi']:>6.1f} {'':>6} "
                  f"{'—':>9}")

    # Highlight any flips today
    flipped = [r for r in rows if r["just_flipped"]]
    if flipped:
        print(f"\n  *** Signal flips today: "
              + ", ".join(f"{r['ticker']} → {'bull' if r['bullish'] else 'bear'}"
                          for r in flipped) + " ***")

    # Entry guidance
    if bullish_rows:
        top = bullish_rows[:3]
        print(f"\n  Entry candidates (run stock_signal.py for sizing):")
        for r in top:
            leverage = "2x margin" if r["stars"] in ("★★★", "★★") else "1x only"
            print(f"    {r['ticker']:<6}  {r['stars']}  {leverage}  "
                  f"({r['days']}d in regime, gap {r['gap_pct']:+.1f}%)")
    print()


def rank(tickers: list[str], ma_fast: int = MA_FAST, ma_slow: int = MA_SLOW):
    print(f"Scanning {len(tickers)} tickers...")
    rows = [r for t in tickers if (r := _scan(t, ma_fast, ma_slow)) is not None]
    if not rows:
        print("No valid results.")
        return
    _print_table(rows, ma_fast, ma_slow)


if __name__ == "__main__":
    args = sys.argv[1:]
    ma_fast, ma_slow = MA_FAST, MA_SLOW

    if "--ma" in args:
        idx     = args.index("--ma")
        parts   = args[idx + 1].split(":")
        ma_fast = int(parts[0])
        ma_slow = int(parts[1])
        args    = [a for j, a in enumerate(args) if j != idx and j != idx + 1]

    tickers = [a.upper() for a in args] if args else DEFAULT_WATCHLIST
    rank(tickers, ma_fast, ma_slow)
