"""
Live signal checker.

Shows current signal state, MA/RSI/MACD values, days in regime,
distance to flip, position sizing, and recent flip history.

Usage:
  python -m tools.signal SPMO
  python -m tools.signal SPMO GLD
  python -m tools.signal SPMO --capital 50000
  python -m tools.signal SPMO GLD --alert            # append machine-readable JSON
  python -m tools.signal SPMO GLD --alert --threshold 3
"""

import json
import sys
from datetime import date

import pandas as pd

from core.data import fetch
from core.config import LEVERAGE, INITIAL_CAPITAL, START
from signals import ma as sig_ma
from signals import rsi as sig_rsi
from signals import macd as sig_macd
from signals.combo import majority_of

from core.portfolio_config import (
    PORTFOLIO as SIGNAL_CONFIGS,
    DEFAULT_SIGNAL as DEFAULT_CONFIG,
    MACD_PARAMS,
)

FLIP_HISTORY = 5


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


def alert_status(ticker: str, prices: pd.Series, cfg: dict,
                 threshold_pct: float = 2.0) -> dict:
    """
    Machine-readable alert state for the daily watcher.

    entered_band_today is True only on the first day the MA gap moves inside
    the near-flip band, so a stateless caller can alert once instead of every
    day the gap hovers there.
    """
    combined  = _build_signal(prices, cfg)
    ma_fast_s = prices.rolling(cfg["ma_fast"]).mean()
    ma_slow_s = prices.rolling(cfg["ma_slow"]).mean()
    dist_pct  = ((ma_fast_s - ma_slow_s).abs() / ma_slow_s * 100).reindex(combined.index)

    in_band = dist_pct < threshold_pct
    days_in_band = 0
    for val in reversed(in_band.values):
        if val:
            days_in_band += 1
        else:
            break

    days_in_regime = 0
    for val in reversed(combined.values[:-1]):
        if val == combined.iloc[-1]:
            days_in_regime += 1
        else:
            break

    return {
        "ticker":             ticker,
        "date":               str(combined.index[-1].date()),
        "signal":             "ON" if combined.iloc[-1] == 1 else "OFF",
        "days_in_regime":     days_in_regime,
        "dist_to_flip_pct":   round(float(dist_pct.iloc[-1]), 2),
        "dist_yesterday_pct": round(float(dist_pct.iloc[-2]), 2),
        "flipped_today":      bool(combined.iloc[-1] != combined.iloc[-2]),
        "entered_band_today": bool(in_band.iloc[-1] and not in_band.iloc[-2]),
        "days_in_band":       days_in_band,
    }


def check(ticker: str, capital: float, prices: pd.Series = None):
    cfg = SIGNAL_CONFIGS.get(ticker, DEFAULT_CONFIG)
    if prices is None:
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


def _portfolio_summary(tickers: list[str], capital: float):
    """Print a one-line portfolio-level action summary when 2+ tickers are checked."""
    if len(tickers) < 2:
        return

    states = {}
    for t in tickers:
        cfg    = SIGNAL_CONFIGS.get(t, DEFAULT_CONFIG)
        prices = fetch(t, start=START)
        if len(prices) < cfg["ma_slow"] + 10:
            continue
        sig = _build_signal(prices, cfg)
        states[t] = {
            "on":     bool(sig.iloc[-1] == 1),
            "weight": cfg.get("weight", 1.0 / len(tickers)),
        }

    if not states:
        return

    on_tickers  = [t for t, s in states.items() if s["on"]]
    off_tickers = [t for t, s in states.items() if not s["on"]]
    on_weight   = sum(states[t]["weight"] for t in on_tickers)

    print(f"\n{'═'*52}")
    print(f"  PORTFOLIO SUMMARY")
    print(f"{'═'*52}")

    if len(on_tickers) == len(states):
        print(f"  ✦ ALL SIGNALS ON — full {LEVERAGE:.0f}x margin on 100% of portfolio")
        print(f"    Deploy ${capital * LEVERAGE:,.0f} total  (${capital:,.0f} own + ${capital*(LEVERAGE-1):,.0f} borrowed)")
    elif not on_tickers:
        print(f"  ◦ ALL SIGNALS OFF — no margin, hold 1x positions")
        print(f"    Hold ${capital:,.0f} unleveraged across all legs")
    else:
        on_str  = " + ".join(f"{t} ({states[t]['weight']:.0%})" for t in on_tickers)
        off_str = " + ".join(f"{t} ({states[t]['weight']:.0%})" for t in off_tickers)
        print(f"  ◑ MIXED — {LEVERAGE:.0f}x on {on_weight:.0%} of portfolio")
        print(f"    Margin ON:  {on_str}")
        print(f"    Margin OFF: {off_str}  (hold 1x)")

    print(f"{'═'*52}\n")


if __name__ == "__main__":
    args    = sys.argv[1:]
    capital = INITIAL_CAPITAL
    if "--capital" in args:
        idx     = args.index("--capital")
        capital = float(args[idx + 1])
        args    = [a for i, a in enumerate(args) if i != idx and i != idx + 1]

    threshold = 2.0
    if "--threshold" in args:
        idx       = args.index("--threshold")
        threshold = float(args[idx + 1])
        args      = [a for i, a in enumerate(args) if i != idx and i != idx + 1]

    alert = "--alert" in args
    args  = [a for a in args if a != "--alert"]

    tickers  = [a.upper() for a in args] if args else ["SPMO"]
    statuses = []
    for t in tickers:
        cfg    = SIGNAL_CONFIGS.get(t, DEFAULT_CONFIG)
        prices = fetch(t, start=START)
        check(t, capital, prices=prices)
        if alert and len(prices) >= cfg["ma_slow"] + 10:
            statuses.append(alert_status(t, prices, cfg, threshold_pct=threshold))

    if len(tickers) > 1:
        _portfolio_summary(tickers, capital)

    if alert:
        print("ALERT_STATUS_JSON")
        print(json.dumps(statuses, indent=2))
