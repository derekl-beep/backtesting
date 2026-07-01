"""
Live signal checker for individual stocks.

Supports three strategies per ticker:
  momentum     — MA crossover (2-tier): 1x bear / 2x bull
  momentum_3t  — MA three-tier: 0x cash / 1x neutral / 2x bull
  mean_rev     — RSI band: 0x cash when neutral/overbought / 1x when oversold

Configure STOCK_CONFIGS below, then run daily.

Usage:
  python -m tools.stock_signal NVDA
  python -m tools.stock_signal NVDA MSFT AAPL
  python -m tools.stock_signal NVDA --capital 50000
"""

import sys
from datetime import date

import pandas as pd

from core.data import fetch
from core.config import LEVERAGE, INITIAL_CAPITAL, START
from signals import ma as sig_ma
from signals import ma_3tier as sig_ma3t
from signals import rsi_band as sig_rsi_band

# Per-ticker signal config.
# strategy options: "momentum" | "momentum_3t" | "mean_rev"
STOCK_CONFIGS = {
    "NVDA": dict(strategy="momentum_3t", fast=50, mid=150, slow=200),
    "MSFT": dict(strategy="momentum",    fast=50, slow=100),
    "AAPL": dict(strategy="momentum",    fast=50, slow=100),
}
DEFAULT_CONFIG = dict(strategy="momentum", fast=50, slow=100)

FLIP_HISTORY = 5

_LEVERAGE_LABEL = {2: f"{LEVERAGE:.0f}x  MARGIN ON", 1: "1x  hold", 0: "0x  CASH"}
_LEVERAGE_ARROW = {2: "▲", 1: "◈", 0: "▼"}


def _regime_days(signal_series, current_val):
    """Count consecutive trailing bars matching current_val."""
    count = 0
    for val in reversed(signal_series.values[:-1]):
        if val == current_val:
            count += 1
        else:
            break
    return count


def _find_flips(signal_series, prices):
    """Return last FLIP_HISTORY state transitions with date, direction, and price."""
    diffs = signal_series.diff().dropna()
    flip_idx = diffs[diffs != 0].index
    events = []
    for d in reversed(flip_idx):
        prev = int(signal_series.loc[d] - diffs.loc[d])
        curr = int(signal_series.loc[d])
        events.append({"date": d, "from": prev, "to": curr, "price": prices.loc[d]})
        if len(events) >= FLIP_HISTORY:
            break
    return events


def _rsi_now(prices, period=14):
    delta = prices.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, float("inf"))
    return (100 - (100 / (1 + rs))).iloc[-1]


# ── Strategy-specific check functions ────────────────────────────────────────

def _check_momentum(ticker, prices, cfg, capital):
    fast, slow = cfg["fast"], cfg["ma_slow"] if "ma_slow" in cfg else cfg["slow"]
    sig        = sig_ma.signal(prices, fast, slow)
    current    = int(sig.iloc[-1])           # 0 or 1 → maps to 1x or 2x
    leverage   = LEVERAGE if current == 1 else 1.0

    ma_fast_s = prices.rolling(fast).mean()
    ma_slow_s = prices.rolling(slow).mean()
    today_price = prices.iloc[-1]
    ma_fast_v   = ma_fast_s.iloc[-1]
    ma_slow_v   = ma_slow_s.iloc[-1]
    gap_pct     = (ma_fast_v - ma_slow_v) / ma_slow_v * 100

    days = _regime_days(sig, current)
    just_flipped = current != int(sig.iloc[-2])

    print(f"\n{'='*54}")
    print(f"  {ticker}  —  {date.today()}")
    print(f"  Strategy : MA{fast}/{slow}  (2-tier momentum)")
    print(f"{'='*54}")
    print(f"  Price    : ${today_price:.2f}")
    print(f"  MA {fast:<3}   : ${ma_fast_v:.2f}")
    print(f"  MA {slow:<3}   : ${ma_slow_v:.2f}")
    print(f"  MA gap   : {gap_pct:+.2f}%")
    print()

    lev_int = 2 if current == 1 else 1
    arrow   = _LEVERAGE_ARROW[lev_int]
    label   = _LEVERAGE_LABEL[lev_int]
    print(f"  SIGNAL  →  {arrow} {label}")
    if just_flipped:
        print(f"  *** FLIPPED TODAY ***")
    else:
        direction = "Bullish" if current == 1 else "Bearish"
        print(f"  {direction} for {days} trading days")

    dist    = abs(ma_fast_v - ma_slow_v)
    action  = "drop" if ma_fast_v > ma_slow_v else "rise"
    print(f"\n  Flip if MA{fast} needs to {action} ~${dist:.2f} ({abs(gap_pct):.1f}%)")

    _print_sizing(capital, today_price, lev_int)
    _print_flips(_find_flips(sig, prices), strategy="momentum")


def _check_momentum_3t(ticker, prices, cfg, capital):
    fast, mid, slow = cfg["fast"], cfg["mid"], cfg["slow"]
    sig   = sig_ma3t.signal(prices, fast, mid, slow)
    current = int(sig.iloc[-1])   # 0, 1, or 2

    ma_fast_s = prices.rolling(fast).mean()
    ma_mid_s  = prices.rolling(mid).mean()
    ma_slow_s = prices.rolling(slow).mean()
    today_price = prices.iloc[-1]
    ma_fast_v   = ma_fast_s.iloc[-1]
    ma_mid_v    = ma_mid_s.iloc[-1]
    ma_slow_v   = ma_slow_s.iloc[-1]

    days = _regime_days(sig, current)
    just_flipped = current != int(sig.iloc[-2])

    print(f"\n{'='*54}")
    print(f"  {ticker}  —  {date.today()}")
    print(f"  Strategy : MA{fast}/{mid}/{slow}  (3-tier momentum)")
    print(f"{'='*54}")
    print(f"  Price    : ${today_price:.2f}")
    print(f"  MA {fast:<3}   : ${ma_fast_v:.2f}")
    print(f"  MA {mid:<3}   : ${ma_mid_v:.2f}")
    print(f"  MA {slow:<3}   : ${ma_slow_v:.2f}")

    gap_fm  = (ma_fast_v - ma_mid_v)  / ma_mid_v  * 100   # fast vs mid
    gap_ms  = (ma_mid_v  - ma_slow_v) / ma_slow_v * 100   # mid vs slow
    print(f"  Fast/mid gap : {gap_fm:+.2f}%")
    print(f"  Mid/slow gap : {gap_ms:+.2f}%")
    print()

    arrow = _LEVERAGE_ARROW[current]
    label = _LEVERAGE_LABEL[current]
    state_desc = {
        2: f"fast({fast}) > mid({mid}) > slow({slow})",
        1: f"mid({mid}) > slow({slow}), fast({fast}) < mid({mid})",
        0: f"mid({mid}) < slow({slow})",
    }[current]
    print(f"  SIGNAL  →  {arrow} {label}")
    print(f"  Condition: {state_desc}")
    if just_flipped:
        print(f"  *** FLIPPED TODAY ***")
    else:
        print(f"  In this regime for {days} trading days")

    print(f"\n  Next transitions:")
    if current == 2:
        dist = abs(ma_fast_v - ma_mid_v)
        print(f"  → 1x if MA{fast} drops ~${dist:.2f} ({abs(gap_fm):.1f}%) below MA{mid}")
        dist2 = abs(ma_mid_v - ma_slow_v)
        print(f"  → 0x if MA{mid} drops ~${dist2:.2f} ({abs(gap_ms):.1f}%) below MA{slow}")
    elif current == 1:
        dist_up = abs(ma_fast_v - ma_mid_v)
        dist_dn = abs(ma_mid_v  - ma_slow_v)
        action_up = "rises" if ma_fast_v < ma_mid_v else "drops"
        print(f"  → 2x if MA{fast} {action_up} ~${dist_up:.2f} ({abs(gap_fm):.1f}%) above MA{mid}")
        print(f"  → 0x if MA{mid} drops ~${dist_dn:.2f} ({abs(gap_ms):.1f}%) below MA{slow}")
    else:
        dist = abs(ma_mid_v - ma_slow_v)
        print(f"  → 1x if MA{mid} rises ~${dist:.2f} ({abs(gap_ms):.1f}%) above MA{slow}")

    _print_sizing(capital, today_price, current)
    _print_flips(_find_flips(sig, prices), strategy="momentum_3t")


def _check_mean_rev(ticker, prices, cfg, capital):
    period   = cfg.get("period",    14)
    oversold = cfg.get("oversold",  30)
    overbought = cfg.get("overbought", 70)

    sig     = sig_rsi_band.signal(prices, period, oversold, overbought)
    current = int(sig.iloc[-1])   # 0 or 1
    rsi_val = _rsi_now(prices, period)

    today_price  = prices.iloc[-1]
    days         = _regime_days(sig, current)
    just_flipped = current != int(sig.iloc[-2])

    print(f"\n{'='*54}")
    print(f"  {ticker}  —  {date.today()}")
    print(f"  Strategy : RSI{period} band {oversold}/{overbought}  (mean-reversion)")
    print(f"{'='*54}")
    print(f"  Price    : ${today_price:.2f}")
    print(f"  RSI({period}) : {rsi_val:.1f}")

    zone = ("oversold ← enter zone" if rsi_val < oversold else
            "overbought ← exit zone" if rsi_val > overbought else
            "neutral")
    print(f"  Zone     : {zone}")
    print()

    lev_label = "1x  IN TRADE" if current == 1 else "0x  CASH"
    arrow     = "◈" if current == 1 else "▼"
    print(f"  SIGNAL  →  {arrow} {lev_label}")
    if just_flipped:
        direction = "ENTERED" if current == 1 else "EXITED"
        print(f"  *** {direction} TODAY ***")
    else:
        state = "In trade" if current == 1 else "Out"
        print(f"  {state} for {days} trading days")

    print(f"\n  RSI thresholds:")
    if current == 0:
        dist_in = rsi_val - oversold
        print(f"  → Enter 1x when RSI < {oversold}  (currently {dist_in:+.1f} pts away)")
    else:
        dist_out = overbought - rsi_val
        print(f"  → Exit to cash when RSI > {overbought}  (currently {dist_out:+.1f} pts away)")
        dist_re  = rsi_val - oversold
        print(f"  → Re-entry if RSI < {oversold}  (currently {dist_re:+.1f} pts away)")

    _print_sizing(capital, today_price, 1 if current == 1 else 0)
    _print_flips(_find_flips(sig, prices), strategy="mean_rev")


# ── Shared print helpers ──────────────────────────────────────────────────────

def _print_sizing(capital, price, leverage_tier):
    print(f"\n  Position sizing  (capital: ${capital:,.0f})")
    print(f"  {'-'*42}")
    if leverage_tier == 2:
        total = capital * LEVERAGE
        shares = total / price
        borrow = capital * (LEVERAGE - 1)
        print(f"  Buy   : {shares:,.1f} shares  (${total:,.0f} total)")
        print(f"  Own   : ${capital:,.0f}  |  Borrow: ${borrow:,.0f}")
    elif leverage_tier == 1:
        shares = capital / price
        print(f"  Buy   : {shares:,.1f} shares  (${capital:,.0f}, no margin)")
    else:
        print(f"  Hold cash: ${capital:,.0f}")


def _print_flips(flips, strategy="momentum"):
    if not flips:
        return
    # Label map depends on strategy
    if strategy == "momentum":
        tier_label = {0: "bear(1x)", 1: "bull(2x)"}
    elif strategy == "momentum_3t":
        tier_label = {0: "cash(0x)", 1: "hold(1x)", 2: "bull(2x)"}
    else:  # mean_rev
        tier_label = {0: "cash(0x)", 1: "in(1x)"}

    print(f"\n  Last {len(flips)} signal transitions:")
    print(f"  {'Date':<12} {'Transition':<20} {'Price':>8}")
    print(f"  {'-'*12} {'-'*20} {'-'*8}")
    for f in flips:
        frm = tier_label.get(f["from"], f"{f['from']}x")
        to  = tier_label.get(f["to"],   f"{f['to']}x")
        print(f"  {str(f['date'].date()):<12} {frm+' → '+to:<20} ${f['price']:>7.2f}")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def check(ticker: str, capital: float):
    cfg    = STOCK_CONFIGS.get(ticker, DEFAULT_CONFIG)
    prices = fetch(ticker, start=START)

    min_len = cfg.get("slow", cfg.get("ma_slow", 100)) + 10
    if len(prices) < min_len:
        print(f"{ticker}: not enough data.")
        return

    strategy = cfg.get("strategy", "momentum")
    if strategy == "momentum_3t":
        _check_momentum_3t(ticker, prices, cfg, capital)
    elif strategy == "mean_rev":
        _check_mean_rev(ticker, prices, cfg, capital)
    else:
        _check_momentum(ticker, prices, cfg, capital)


if __name__ == "__main__":
    args    = sys.argv[1:]
    capital = INITIAL_CAPITAL

    if "--capital" in args:
        idx     = args.index("--capital")
        capital = float(args[idx + 1])
        args    = [a for i, a in enumerate(args) if i != idx and i != idx + 1]

    tickers = [a.upper() for a in args] if args else list(STOCK_CONFIGS.keys())
    for t in tickers:
        check(t, capital)
