"""Regime classification.

Three orthogonal regime axes, each soft-encoded (no hard categorical bucketing
inside the state vector — softness preserves continuity for similarity search).

  trend strength    : ADX-like, normalized to [0, 1]
  vol regime        : where current realized vol sits in its 252d rank (0..1)
  chop / mean-rev   : 1 - |price-path-efficiency|, in [0, 1]

Plus discrete one-hot flags for "high vol" and "trend up/down" for users that
want to filter by regime explicitly.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _wilder_smooth(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(alpha=1 / period, adjust=False).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    up = high.diff()
    down = -low.diff()
    plus_dm = ((up > down) & (up > 0)).astype(float) * up.clip(lower=0)
    minus_dm = ((down > up) & (down > 0)).astype(float) * down.clip(lower=0)

    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr = _wilder_smooth(tr, period)

    plus_di = 100 * _wilder_smooth(plus_dm, period) / atr
    minus_di = 100 * _wilder_smooth(minus_dm, period) / atr
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    return _wilder_smooth(dx, period)


def encode_regime(prices: pd.DataFrame) -> pd.DataFrame:
    close = prices["close"]
    high = prices["high"]
    low = prices["low"]

    out = pd.DataFrame(index=prices.index)

    adx = _adx(high, low, close)
    out["reg_adx_norm"] = (adx / 100.0).clip(0, 1)

    # Trend direction: sign of slope of 50d linear regression, scaled
    log_close = np.log(close)
    slope50 = log_close.diff().rolling(50).mean() * 252  # annualized log-return
    out["reg_trend_dir"] = np.tanh(slope50 / 0.30)  # ~−1..+1, saturates at 30% annualized

    # Vol percentile rank over a year — captures "is this calm or panicked?"
    log_ret = np.log(close / close.shift(1))
    rv21 = log_ret.rolling(21).std() * np.sqrt(252)
    out["reg_vol_rank252"] = rv21.rolling(252).rank(pct=True)

    # Path efficiency: |net move| / sum |daily moves|. High = trend, low = chop.
    net_move = (close - close.shift(21)).abs()
    sum_moves = close.diff().abs().rolling(21).sum()
    eff = net_move / sum_moves.replace(0, np.nan)
    out["reg_path_efficiency_21"] = eff.clip(0, 1)
    out["reg_chop_21"] = 1.0 - out["reg_path_efficiency_21"]

    # Drawdown depth from 252d high — risk-off detector
    rolling_max = close.rolling(252).max()
    out["reg_dd_252"] = (close / rolling_max - 1).clip(lower=-1, upper=0)

    return out
