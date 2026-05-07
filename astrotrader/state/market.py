"""Market-side features. Returns, volatility, momentum, liquidity proxies.

All features are constructed strictly from the past so they are usable in
walk-forward back-tests without lookahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def encode_market(prices: pd.DataFrame) -> pd.DataFrame:
    """Return wide feature DataFrame indexed identically to prices."""
    close = prices["close"]
    high = prices["high"]
    low = prices["low"]
    vol = prices["volume"].astype(float)

    log_ret = np.log(close / close.shift(1))

    out = pd.DataFrame(index=prices.index)

    # Returns over multiple lookbacks
    out["mkt_ret_1"] = log_ret
    out["mkt_ret_5"] = log_ret.rolling(5).sum()
    out["mkt_ret_21"] = log_ret.rolling(21).sum()
    out["mkt_ret_63"] = log_ret.rolling(63).sum()

    # Realized volatility (annualized)
    out["mkt_rv_21"] = log_ret.rolling(21).std() * np.sqrt(252)
    out["mkt_rv_63"] = log_ret.rolling(63).std() * np.sqrt(252)

    # ATR normalized by close (true-range as % of price)
    out["mkt_atr_pct_14"] = _atr(high, low, close, 14) / close

    # Momentum
    out["mkt_rsi_14"] = _rsi(close, 14) / 100.0
    macd = _ema(close, 12) - _ema(close, 26)
    out["mkt_macd_norm"] = macd / close
    out["mkt_macd_hist"] = (macd - _ema(macd, 9)) / close

    # Distance from moving averages (% deviation; mean-reverters love this)
    out["mkt_dist_sma50"] = close / close.rolling(50).mean() - 1
    out["mkt_dist_sma200"] = close / close.rolling(200).mean() - 1

    # Liquidity proxy: dollar volume z-score over 60d
    dv = close * vol
    out["mkt_dv_z60"] = (dv - dv.rolling(60).mean()) / dv.rolling(60).std()

    # Skew/kurt of recent returns — cheap tail-risk hints
    out["mkt_skew_21"] = log_ret.rolling(21).skew()
    out["mkt_kurt_21"] = log_ret.rolling(21).kurt()

    # Realized range relative to vol — compression detector
    daily_range = (high - low) / close
    out["mkt_range_z21"] = (
        (daily_range - daily_range.rolling(21).mean()) / daily_range.rolling(21).std()
    )

    return out
