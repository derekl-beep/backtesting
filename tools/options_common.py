"""
Shared helpers for building a call-options overlay on an arbitrary ticker's own
signal, used by options_chain_check.py, options_bootstrap.py, options_sensitivity.py,
and portfolio_combined.py. Factored out after those four tools independently
reimplemented the same "resolve signal/call prices, IV proxy, and params for
ticker X" logic with slight variations.
"""

from core.data import fetch
from core.portfolio_config import PORTFOLIO, resolve_signal_params
import signals.ma as sig_ma
from tools.options_backtest import SIGNAL_TICKER, CALL_TICKER, IV_TICKER, _get_regimes

# Ticker -> real listed implied-vol index. Tickers not listed here fall back to a
# trailing realized-vol proxy (see iv_proxy_series below).
KNOWN_IV_PROXIES = {
    "QQQ": "^VIX",
    "GLD": "^GVZ",
}


def iv_proxy_series(ticker: str, prices):
    """
    Full time-indexed IV proxy series for `ticker` (percent scale, matching the
    ^VIX/^GVZ convention) -- the real listed vol index if one is configured in
    KNOWN_IV_PROXIES, otherwise a trailing 21-day realized-vol series computed
    from `prices` itself.
    """
    proxy_ticker = KNOWN_IV_PROXIES.get(ticker)
    if proxy_ticker:
        return fetch(proxy_ticker)
    ret = prices.pct_change()
    return (ret.rolling(21).std() * (252 ** 0.5) * 100).bfill()


def overlay_inputs(ticker: str):
    """
    Resolve everything needed to backtest `ticker`'s call-options overlay: its
    own signal -> own calls, or the shipped SPMO -> QQQ cross-ticker overlay
    when ticker == SIGNAL_TICKER. Params come from core.portfolio_config's
    single resolution path (live portfolio -> researched candidates -> generic
    fallback), so this always matches what every other tool would use.

    Returns (call_prices, iv_prices, regimes, label).
    """
    if ticker == SIGNAL_TICKER:
        signal_prices = fetch(SIGNAL_TICKER)
        call_prices   = fetch(CALL_TICKER)
        iv_prices     = fetch(IV_TICKER)
        cfg           = PORTFOLIO[SIGNAL_TICKER]
        label         = f"{SIGNAL_TICKER}→{CALL_TICKER}"
    else:
        signal_prices = fetch(ticker)
        call_prices   = signal_prices
        cfg           = resolve_signal_params(ticker)
        iv_prices     = iv_proxy_series(ticker, signal_prices)
        label         = f"{ticker}→{ticker}"

    signal  = sig_ma.signal(signal_prices, cfg["ma_fast"], cfg["ma_slow"])
    regimes = _get_regimes(signal)
    return call_prices, iv_prices, regimes, label
