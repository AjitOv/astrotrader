"""Forward-outcome computation.

For each historical date, precompute:
  fwd_logret_h  : log return over the next h trading days
  fwd_maxdd_h   : maximum drawdown observed inside the next h days
  fwd_maxup_h   : maximum favorable excursion inside the next h days
  fwd_realvol_h : realized volatility of daily returns over the next h days

Stored as a wide DataFrame aligned to the price index.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import SETTINGS


def compute_forward(prices: pd.DataFrame, horizons: tuple[int, ...] | None = None) -> pd.DataFrame:
    horizons = horizons or SETTINGS.horizons.days
    close = prices["close"]
    log_close = np.log(close)
    log_ret = log_close.diff()

    out = pd.DataFrame(index=prices.index)

    for h in horizons:
        # Forward log return: log(close[t+h] / close[t])
        out[f"fwd_logret_{h}"] = log_close.shift(-h) - log_close

        # Realized vol over next h days (daily stdev × sqrt(252))
        # Build by reversing the rolling window: shift(-h) so the window
        # at row t covers rows [t+1 .. t+h].
        forward_returns = log_ret.shift(-h).rolling(h).std() * np.sqrt(252)
        # That actually anchors at t+h. To anchor at t: take shift back.
        # Simpler: compute via cumulative trick.
        out[f"fwd_realvol_{h}"] = _forward_rolling_std(log_ret, h) * np.sqrt(252)

        # Forward max drawdown / max favorable excursion within the horizon.
        out[f"fwd_maxdd_{h}"] = _forward_path_extremum(log_close, h, kind="dd")
        out[f"fwd_maxup_{h}"] = _forward_path_extremum(log_close, h, kind="up")

    return out


def _forward_rolling_std(s: pd.Series, h: int) -> pd.Series:
    """Std of s over (t, t+h]. Anchored at t."""
    # Reverse, take rolling std, reverse back
    rev = s[::-1]
    rstd = rev.rolling(h).std()[::-1]
    return rstd.shift(-1)  # window covers t+1..t+h


def _forward_path_extremum(log_close: pd.Series, h: int, kind: str) -> pd.Series:
    """Forward max drawdown ('dd', negative) or max favorable excursion ('up', positive)
    measured in log-return space, observed inside (t, t+h].
    """
    arr = log_close.to_numpy()
    n = len(arr)
    out = np.full(n, np.nan)

    for t in range(n - h):
        path = arr[t + 1 : t + 1 + h]
        if kind == "dd":
            running_max = np.maximum.accumulate(path)
            out[t] = float(np.min(path - running_max))  # ≤ 0
        else:
            running_min = np.minimum.accumulate(path)
            out[t] = float(np.max(path - running_min))  # ≥ 0

    return pd.Series(out, index=log_close.index)
