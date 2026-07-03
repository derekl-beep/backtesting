"""
Live options trade recommendation based on current SPMO signal.

When SPMO is bullish, recommends a specific QQQ call to buy:
  - Nearest available QQQ expiry ~6 months out
  - ATM strike (Δ0.50) priced with Black-Scholes + current VIX
  - Contract count and total cost at 3%, 5%, 10% budget levels
  - Regime context: days in bull run, QQQ performance since entry
  - If regime is old enough to have rolled, shows which leg you'd be in
  - If within 30 DTE on current leg: shows roll recommendation

When SPMO is bearish, notes no options action and shows bear duration.

Usage:
  python -m tools.options_signal
  python -m tools.options_signal --capital 150000
  python -m tools.options_signal --delta 0.30     # OTM calls instead
"""

import math
import sys
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from core.config import INITIAL_CAPITAL
from core.data import fetch
from core.portfolio_config import PORTFOLIO
from signals import ma as sig_ma
from tools.options_backtest import (
    CALL_TICKER, RISK_FREE_RATE, ROLL_DTE, SIGNAL_TICKER, SPREAD_COST,
    TENOR_DAYS, bs_call, bs_delta, strike_for_delta,
)

DISPLAY_BUDGETS = [0.03, 0.05, 0.10]


def _regime_start(signal: pd.Series) -> pd.Timestamp | None:
    """Return the first date of the current bull regime, or None if bearish."""
    if signal.iloc[-1] != 1:
        return None
    for i in range(len(signal) - 2, -1, -1):
        if signal.iloc[i] != 1:
            return signal.index[i + 1]
    return signal.index[0]


def _nearest_expiry(ticker: str, target_days: int = TENOR_DAYS) -> str | None:
    """Find the nearest real options expiry to target_days from today."""
    try:
        expiries = yf.Ticker(ticker).options
        if not expiries:
            return None
        target = date.today() + timedelta(days=target_days)
        return min(expiries, key=lambda e: abs((date.fromisoformat(e) - target).days))
    except Exception:
        return None


def _current_vix() -> float:
    try:
        vix = fetch("^VIX")
        return float(vix.iloc[-1])
    except Exception:
        return 20.0


def _leg_number(regime_start: pd.Timestamp) -> tuple[int, int]:
    """
    Given regime start, return (current_leg, days_into_leg).
    Leg 1 = first 150 days, Leg 2 = next 150 days, etc.
    """
    days_in = (pd.Timestamp.today() - regime_start).days
    roll_window = TENOR_DAYS - ROLL_DTE
    leg = days_in // roll_window + 1
    days_into_leg = days_in % roll_window
    return int(leg), int(days_into_leg)


def _dte_remaining(regime_start: pd.Timestamp) -> int:
    """Days to expiry on the current leg's option."""
    _, days_into_leg = _leg_number(regime_start)
    roll_window = TENOR_DAYS - ROLL_DTE
    return TENOR_DAYS - days_into_leg


def _qqq_since_regime(qqq_prices: pd.Series, regime_start: pd.Timestamp) -> float | None:
    dates = qqq_prices.index
    idx = dates.searchsorted(regime_start)
    if idx >= len(dates):
        return None
    entry_price = float(qqq_prices.iloc[idx])
    current_price = float(qqq_prices.iloc[-1])
    return current_price / entry_price - 1


def _unrealized_call(qqq_prices, vix_prices, regime_start, target_delta):
    """
    Estimate unrealized P&L on the current leg of the rolling strategy.
    Returns dict with entry/current values, or None.
    """
    leg, days_into_leg = _leg_number(regime_start)
    roll_window = TENOR_DAYS - ROLL_DTE

    # start of the current leg
    leg_start = regime_start + pd.Timedelta(days=(leg - 1) * roll_window)
    dates = qqq_prices.index
    leg_idx = dates.searchsorted(leg_start)
    if leg_idx >= len(dates):
        return None

    leg_start_ts = dates[leg_idx]
    S_entry = float(qqq_prices.iloc[leg_idx])
    vix_val = float(vix_prices.reindex(dates, method="ffill").iloc[leg_idx])
    sigma_entry = max(vix_val / 100.0, 0.05)

    T_entry = TENOR_DAYS / 365.0
    K = strike_for_delta(S_entry, T_entry, RISK_FREE_RATE, sigma_entry, target_delta)
    price_entry = bs_call(S_entry, K, T_entry, RISK_FREE_RATE, sigma_entry)

    # current value
    S_now = float(qqq_prices.iloc[-1])
    T_now = max((_dte_remaining(regime_start)) / 365.0, 0.0)
    vix_now = float(vix_prices.reindex(dates, method="ffill").iloc[-1])
    sigma_now = max(vix_now / 100.0, 0.05)
    price_now = bs_call(S_now, K, T_now, RISK_FREE_RATE, sigma_now)

    return {
        "leg":          leg,
        "leg_start":    str(leg_start_ts.date()),
        "K":            K,
        "S_entry":      S_entry,
        "S_now":        S_now,
        "price_entry":  price_entry,
        "price_now":    price_now,
        "pnl_pct":      (price_now - price_entry) / price_entry if price_entry > 0 else 0,
        "dte":          _dte_remaining(regime_start),
        "vix_entry":    vix_val,
        "vix_now":      vix_now,
    }


def recommend(capital: float = INITIAL_CAPITAL, target_delta: float = 0.50):
    cfg     = PORTFOLIO[SIGNAL_TICKER]
    spmo    = fetch(SIGNAL_TICKER)
    qqq     = fetch(CALL_TICKER)
    vix_s   = fetch("^VIX")

    signal  = sig_ma.signal(spmo, cfg["ma_fast"], cfg["ma_slow"])
    bullish = bool(signal.iloc[-1] == 1)
    today   = date.today()

    print(f"\n{'='*60}")
    print(f"  Options trade recommendation  —  {today}")
    print(f"  Signal source: SPMO MA{cfg['ma_fast']}/{cfg['ma_slow']}")
    print(f"{'='*60}")

    if not bullish:
        # bear regime
        bear_days = 0
        for val in reversed(signal.values[:-1]):
            if val == 0:
                bear_days += 1
            else:
                break
        print(f"\n  SIGNAL: ◦ BEARISH  ({bear_days} trading days in bear regime)")
        print(f"\n  No options position recommended.")
        print(f"  Hold cash. Wait for SPMO MA{cfg['ma_fast']} to cross above MA{cfg['ma_slow']}.")
        print()
        return

    # bull regime
    regime_start = _regime_start(signal)
    days_in = (pd.Timestamp.today() - regime_start).days if regime_start else 0
    leg, days_into_leg = _leg_number(regime_start) if regime_start else (1, 0)
    dte = _dte_remaining(regime_start) if regime_start else TENOR_DAYS
    roll_window = TENOR_DAYS - ROLL_DTE

    qqq_ret = _qqq_since_regime(qqq, regime_start) if regime_start else None
    vix_now = _current_vix()
    S_now   = float(qqq.iloc[-1])
    sigma   = max(vix_now / 100.0, 0.05)

    print(f"\n  SIGNAL: ✦ BULLISH")
    print(f"  Bull regime started: {regime_start.date() if regime_start else 'unknown'}"
          f"  ({days_in} calendar days ago)")
    if qqq_ret is not None:
        print(f"  QQQ since entry:     {qqq_ret:+.1%}")
    print(f"  Current leg:         #{leg}  ({days_into_leg} days into this 150-day leg)")
    print(f"  VIX (IV proxy):      {vix_now:.1f}")

    # roll warning
    if dte <= ROLL_DTE:
        print(f"\n  ⚠  ROLL DUE — {dte} DTE remaining on current leg.")
        print(f"     Close existing call and open a new one (see recommendation below).")
    elif dte <= ROLL_DTE + 10:
        print(f"\n  ⚠  Roll approaching — {dte} DTE remaining.")

    # option recommendation
    T = TENOR_DAYS / 365.0
    K = strike_for_delta(S_now, T, RISK_FREE_RATE, sigma, target_delta)
    price = bs_call(S_now, K, T, RISK_FREE_RATE, sigma)
    actual_delta = bs_delta(S_now, K, T, RISK_FREE_RATE, sigma)

    # try to find a real expiry from the chain
    real_expiry = _nearest_expiry(CALL_TICKER, TENOR_DAYS)
    expiry_str  = real_expiry if real_expiry else str(today + timedelta(days=TENOR_DAYS))

    print(f"\n  {'─'*56}")
    print(f"  RECOMMENDED TRADE: BUY TO OPEN")
    print(f"  {'─'*56}")
    print(f"  Instrument:   {CALL_TICKER} call")
    print(f"  Expiry:       {expiry_str}  (~{TENOR_DAYS} days)")
    print(f"  Strike:       ${K:.0f}  (Δ{actual_delta:.2f})")
    print(f"  Est. premium: ${price:.2f}/share  =  ${price*100:.0f}/contract")
    print(f"  IV (VIX):     {vix_now:.1f}  →  σ {sigma:.0%}/yr")

    print(f"\n  Sizing at different budget levels  (capital: ${capital:,.0f})")
    print(f"  {'Budget':>8}  {'Premium $':>10}  {'Contracts':>10}  {'Total cost':>12}")
    print(f"  {'─'*46}")
    contract_cost = price * 100 * (1 + SPREAD_COST)
    for bf in DISPLAY_BUDGETS:
        budget = capital * bf
        n      = int(budget / (price * 100))
        if n < 1:
            pct_needed = contract_cost / capital
            print(f"  {bf:>7.0%}  ${budget:>9,.0f}  {'—':>10}  "
                  f"below 1-contract min (${contract_cost:,.0f} = {pct_needed:.0%} of capital)")
            continue
        total = n * contract_cost
        print(f"  {bf:>7.0%}  ${budget:>9,.0f}  {n:>10}  ${total:>11,.0f}")

    # unrealized P&L on current leg
    unreal = _unrealized_call(qqq, vix_s, regime_start, target_delta) if regime_start else None
    if unreal and leg == unreal["leg"]:
        print(f"\n  Current leg unrealized P&L (if entered at leg start):")
        print(f"  Leg #{unreal['leg']} started: {unreal['leg_start']}  "
              f"K=${unreal['K']:.0f}  entry prem ${unreal['price_entry']:.2f}")
        print(f"  QQQ: ${unreal['S_entry']:.2f} → ${unreal['S_now']:.2f}  "
              f"Call: ${unreal['price_entry']:.2f} → ${unreal['price_now']:.2f}  "
              f"({unreal['pnl_pct']:+.0%})")
        print(f"  DTE remaining: {unreal['dte']} days  "
              f"VIX at entry: {unreal['vix_entry']:.1f}  now: {unreal['vix_now']:.1f}")

    print(f"\n  Exit trigger: close when SPMO MA{cfg['ma_fast']} crosses below MA{cfg['ma_slow']}")
    print(f"  Roll trigger: roll when ≤{ROLL_DTE} DTE on current leg")
    print()


if __name__ == "__main__":
    args    = sys.argv[1:]
    capital = INITIAL_CAPITAL
    delta   = 0.50

    if "--capital" in args:
        idx     = args.index("--capital")
        capital = float(args[idx + 1])
        args    = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    if "--delta" in args:
        idx   = args.index("--delta")
        delta = float(args[idx + 1])
        args  = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    recommend(capital=capital, target_delta=delta)
