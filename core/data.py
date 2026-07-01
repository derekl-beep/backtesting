import yfinance as yf
import pandas as pd
from core.config import START


def fetch(ticker: str, start: str = START, period: str = None) -> pd.Series:
    """Fetch daily close prices for a ticker. Returns a named Series."""
    kwargs = dict(auto_adjust=True, progress=False)
    if period:
        raw = yf.download(ticker, period=period, **kwargs)
    else:
        raw = yf.download(ticker, start=start, **kwargs)
    prices = raw["Close"].squeeze().dropna()
    prices.name = ticker
    return prices
