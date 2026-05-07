"""OHLC price loader. yfinance for free historical data, parquet cache.

Friendly names → yfinance tickers. The user-facing symbol passed everywhere
in the system is a clean, marketing-grade label (e.g. "NIFTY", "BTCUSD"),
which we translate to yfinance's convention ("^NSEI", "BTC-USD") only at the
download boundary. The cache file is keyed by the friendly name so paths stay
filesystem-safe.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import yfinance as yf

from ..config import SETTINGS

log = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]

# Friendly user-facing symbol → yfinance ticker.
# Anything not in this map is passed through unchanged so power users can
# still pass raw yfinance tickers if they want to.
SYMBOL_MAP: dict[str, str] = {
    # US ETFs (identity — included for documentation)
    "SPY": "SPY",
    "QQQ": "QQQ",
    "IWM": "IWM",
    "GLD": "GLD",
    "USO": "USO",
    # Indian indices
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    # Indian large-caps (NSE)
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "HDFCBANK": "HDFCBANK.NS",
    # Crypto
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    # Commodities / FX
    "XAUUSD": "GC=F",  # spot gold via continuous futures (most reliable in yfinance)
}


def resolve_ticker(symbol: str) -> str:
    """Translate a user-facing symbol to its yfinance ticker."""
    return SYMBOL_MAP.get(symbol.upper(), symbol)


def _cache_path(symbol: str) -> Path:
    return SETTINGS.cache_dir / f"prices_{symbol.upper()}.parquet"


def load_prices(
    symbol: str = "SPY",
    start: str | None = None,
    end: str | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Load daily OHLCV. Returns DataFrame indexed by tz-naive date with lowercase columns.

    Cached on disk as parquet (keyed by the friendly symbol). Pass refresh=True
    to re-download.
    """
    start = start or SETTINGS.default_history_start
    path = _cache_path(symbol)
    yf_ticker = resolve_ticker(symbol)

    if path.exists() and not refresh:
        df = pd.read_parquet(path)
    else:
        log.info("downloading %s (yfinance: %s)", symbol, yf_ticker)
        raw = yf.download(yf_ticker, start=start, end=end, progress=False, auto_adjust=True)
        if raw.empty:
            raise RuntimeError(f"no price data for {symbol} (yfinance: {yf_ticker})")
        # yfinance sometimes returns a column MultiIndex; flatten.
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw.columns = [c.lower() for c in raw.columns]
        df = raw[REQUIRED_COLUMNS].copy()
        df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
        df.index.name = "date"
        df.to_parquet(path)

    if start:
        df = df.loc[df.index >= pd.Timestamp(start)]
    if end:
        df = df.loc[df.index <= pd.Timestamp(end)]
    return df
