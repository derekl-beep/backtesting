"""
Validate the options-backtest pricing model against a real, live option chain.

Everything in tools/options_backtest.py and tools/options_signal.py prices options
with Black-Scholes fed by a proxy IV (^VIX for QQQ, ^GVZ for GLD, trailing realized
vol for tickers with no listed vol index). None of it has ever been checked against
a real quoted option chain -- real strikes, real bid/ask, real open interest. This
tool pulls the real chain nearest our modeled tenor/delta and prints the model price,
proxy IV, and assumed spread cost next to what the market actually shows.

Usage:
  python -m tools.options_chain_check              # QQQ (the shipped SPMO overlay underlying)
  python -m tools.options_chain_check QQQ GLD SMH
  python -m tools.options_chain_check SMH --delta 0.30
  python -m tools.options_chain_check GLD --tenor 90
"""

import sys
from datetime import date

import pandas as pd
import yfinance as yf

from core.data import fetch, SESSION
from tools.options_backtest import (
    RISK_FREE_RATE, SPREAD_COST, TENOR_DAYS,
    bs_call, bs_delta, strike_for_delta, _realized_vol,
)

# Ticker -> real listed implied-vol index. Tickers not listed here fall back to a
# trailing realized-vol proxy (see tools/options_backtest.py's own fallback for SMH).
KNOWN_IV_PROXIES = {
    "QQQ": "^VIX",
    "GLD": "^GVZ",
}

MIN_LIQUID_OI = 50   # open interest below this is a real-world liquidity warning


def _model_iv(ticker: str, prices: pd.Series) -> tuple[float, str]:
    """Return (annualized IV as a fraction, description of the proxy used)."""
    proxy_ticker = KNOWN_IV_PROXIES.get(ticker)
    if proxy_ticker:
        proxy = fetch(proxy_ticker)
        return float(proxy.iloc[-1]) / 100.0, f"{proxy_ticker} (listed implied-vol index)"
    sigma = _realized_vol(prices, prices.index[-1])
    return sigma, "trailing 21-day realized vol (no listed vol index for this ticker)"


def iv_proxy_series(ticker: str, prices: pd.Series) -> pd.Series:
    """
    Full time-indexed IV proxy series for `ticker` (percent scale, matching the
    ^VIX/^GVZ convention) -- the real listed vol index if one is configured in
    KNOWN_IV_PROXIES, otherwise a trailing 21-day realized-vol series computed
    from `prices` itself. Shared by any tool that needs IV history (not just a
    single as-of-today value) for a ticker with no listed vol index.
    """
    proxy_ticker = KNOWN_IV_PROXIES.get(ticker)
    if proxy_ticker:
        return fetch(proxy_ticker)
    ret = prices.pct_change()
    return (ret.rolling(21).std() * (252 ** 0.5) * 100).bfill()


def _nearest_expiry(ticker: str, target_days: int):
    expiries = yf.Ticker(ticker, session=SESSION).options
    if not expiries:
        return None
    target = date.today().toordinal() + target_days
    return min(expiries, key=lambda e: abs(date.fromisoformat(e).toordinal() - target))


def check(ticker: str, target_delta: float = 0.50, tenor_days: int = TENOR_DAYS):
    prices = fetch(ticker, use_cache=False, period="5d")
    if prices.empty:
        print(f"\n{ticker}: could not fetch a current price.")
        return
    S = float(prices.iloc[-1])
    sigma_model, proxy_desc = _model_iv(ticker, prices)

    expiry = _nearest_expiry(ticker, tenor_days)
    if not expiry:
        print(f"\n{ticker}: no listed options found (yfinance returned no expiries).")
        return

    dte = (date.fromisoformat(expiry) - date.today()).days
    T = dte / 365.0

    chain = yf.Ticker(ticker, session=SESSION).option_chain(expiry)
    calls = chain.calls
    if calls.empty:
        print(f"\n{ticker}: expiry {expiry} returned an empty call chain.")
        return

    # Strike our model would pick for target_delta, then snap to the nearest
    # strike that's actually listed (real chains are discrete, not continuous).
    model_K = strike_for_delta(S, T, RISK_FREE_RATE, sigma_model, target_delta)
    calls = calls.assign(_dist=(calls["strike"] - model_K).abs())
    row = calls.sort_values("_dist").iloc[0]

    K          = float(row["strike"])
    real_iv    = float(row["impliedVolatility"])
    bid, ask   = float(row["bid"]), float(row["ask"])
    last       = float(row["lastPrice"])
    oi         = int(row["openInterest"]) if pd.notna(row["openInterest"]) else 0
    volume     = int(row["volume"]) if pd.notna(row["volume"]) else 0
    real_mid   = (bid + ask) / 2 if bid > 0 and ask > 0 else last
    real_spread_pct = (ask - bid) / real_mid if real_mid > 0 and ask > bid else None

    model_price      = bs_call(S, K, T, RISK_FREE_RATE, sigma_model)
    model_price_realiv = bs_call(S, K, T, RISK_FREE_RATE, real_iv)
    real_delta       = bs_delta(S, K, T, RISK_FREE_RATE, real_iv)

    print(f"\n{'='*66}")
    print(f"  {ticker}  —  real option chain vs. backtest model")
    print(f"{'='*66}")
    print(f"  Spot price       : ${S:.2f}")
    print(f"  Expiry checked   : {expiry}  ({dte} DTE, target was {tenor_days})")
    print(f"  Strike           : ${K:.0f}  (target Δ{target_delta:.2f}, model picked "
          f"${model_K:.0f} → snapped to nearest listed strike)")
    print(f"  Real delta       : {real_delta:.2f}")
    print()
    print(f"  IV               : model {sigma_model:.1%} ({proxy_desc})")
    print(f"                     real  {real_iv:.1%} (yfinance impliedVolatility)")
    print(f"                     diff  {real_iv - sigma_model:+.1%} pts")
    print()
    print(f"  Price            : model (proxy IV)  ${model_price:.2f}")
    print(f"                     model (real IV)   ${model_price_realiv:.2f}")
    print(f"                     real  bid/ask      ${bid:.2f} / ${ask:.2f}  "
          f"(mid ${real_mid:.2f}, last ${last:.2f})")
    if real_mid > 0:
        diff_pct = (model_price - real_mid) / real_mid
        print(f"                     model vs real mid  {diff_pct:+.1%}")
    print()
    if real_spread_pct is not None:
        print(f"  Bid-ask spread   : real {real_spread_pct:.1%} of mid   "
              f"vs. assumed SPREAD_COST {SPREAD_COST:.1%} in the backtest"
              f"{'  ⚠ real spread much wider' if real_spread_pct > SPREAD_COST * 3 else ''}")
    else:
        print(f"  Bid-ask spread   : no valid bid/ask quoted (illiquid)")
    print(f"  Liquidity        : open interest {oi}, volume {volume}"
          f"{'  ⚠ thin — real fills may slip from quoted price' if oi < MIN_LIQUID_OI else ''}")
    print()


if __name__ == "__main__":
    args = sys.argv[1:]
    delta = 0.50
    tenor = TENOR_DAYS

    if "--delta" in args:
        idx = args.index("--delta")
        delta = float(args[idx + 1])
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]
    if "--tenor" in args:
        idx = args.index("--tenor")
        tenor = int(args[idx + 1])
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    tickers = [a.upper() for a in args if not a.startswith("--")] or ["QQQ"]
    for t in tickers:
        check(t, target_delta=delta, tenor_days=tenor)
