"""
Price data with a market-close-aware local cache.

fetch() serves from data/{ticker}.pkl when the cache was written after the
most recent NYSE close (4pm ET, weekdays) — so intraday reruns and optimizer
sweeps hit the network once per ticker per trading day, and every run within
a day sees identical history. The full history is always re-downloaded rather
than tail-appended: adjusted close is rescaled retroactively on each dividend,
so incremental appends would silently corrupt the series.
"""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yfinance as yf
import pandas as pd

from core.config import START

CACHE_DIR = Path(__file__).parent.parent / "data"
_ET = ZoneInfo("America/New_York")


def _last_market_close() -> datetime:
    """Most recent weekday 4pm ET before now (holidays ignored — worst case
    is one redundant refetch on a market holiday)."""
    now = datetime.now(_ET)
    close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    if now < close:
        close -= timedelta(days=1)
    while close.weekday() >= 5:
        close -= timedelta(days=1)
    return close


def _cache_is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, _ET)
    return mtime > _last_market_close()


def _download(ticker: str, start: str = None, period: str = None) -> pd.Series:
    kwargs = dict(auto_adjust=True, progress=False)
    if period:
        raw = yf.download(ticker, period=period, **kwargs)
    else:
        raw = yf.download(ticker, start=start, **kwargs)
    prices = raw["Close"].squeeze().dropna()
    prices.name = ticker
    return prices


def fetch(ticker: str, start: str = START, period: str = None,
          use_cache: bool = True) -> pd.Series:
    """Fetch daily adjusted close prices for a ticker. Returns a named Series."""
    # Only the standard full-history query is cacheable
    if period or start < START or not use_cache:
        return _download(ticker, start=start, period=period)

    cache_file = CACHE_DIR / f"{ticker}.pkl"
    if _cache_is_fresh(cache_file):
        prices = pd.read_pickle(cache_file)
    else:
        prices = _download(ticker, start=START)
        if len(prices):
            CACHE_DIR.mkdir(exist_ok=True)
            prices.to_pickle(cache_file)

    return prices[prices.index >= start]
