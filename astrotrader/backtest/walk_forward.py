"""Walk-forward backtest runner.

For each trading day t in [start, end] we:
  1. call decide(t)           — query state(t) against history < (t - min_lookback)
  2. read realized fwd_logret_h from the precomputed forward DataFrame
  3. record one row of (predicted, realized)

Leakage notes
-------------
* The similarity engine respects `min_lookback_days` so matches at t never come
  from the trailing window around t. This is the primary leakage guard.
* The StateMatrix's z-score means/stds are computed over the FULL training
  window, including dates after t. This is a small distortion (column scale,
  not column ordering) and acceptable for v1. A future "true walk-forward
  normalization" mode can recompute means/stds expanding-window if calibration
  reveals a problem.
* Forward returns are by definition future-looking — but only consumed for
  matched (older) dates whose horizon has fully elapsed by t.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..pipeline import AstrotradeContext, decide

log = logging.getLogger(__name__)


@dataclass
class BacktestRow:
    date: pd.Timestamp
    horizon: int
    p_up: float                 # calibrated when ctx has a calibrator; equal to p_up_raw otherwise
    p_up_raw: float             # always the uncalibrated bundle weighted-vote
    p_down: float
    bias: str
    confidence: float
    calibrated: bool
    expected_logret: float
    expected_realvol: float
    sample_size: int
    effective_sample_size: float
    contrib_astro: float
    contrib_market: float
    contrib_regime: float
    actual_logret: float
    actual_up: int


def walk_forward(
    ctx: AstrotradeContext,
    horizon: int = 5,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    top_n: int = 50,
    stride: int = 1,
    progress_callback=None,
) -> pd.DataFrame:
    """Run walk-forward and return a DataFrame of one row per date.

    stride > 1 means evaluate every k-th trading day — useful for fast iteration
    or when horizons overlap and you want non-overlapping samples.
    """
    fwd_col = f"fwd_logret_{horizon}"
    if fwd_col not in ctx.forward.columns:
        raise ValueError(
            f"horizon {horizon} not in precomputed forward returns "
            f"(columns: {list(ctx.forward.columns)})"
        )

    dates = ctx.state_matrix.dates
    in_window = np.ones(len(dates), dtype=bool)
    if start is not None:
        in_window &= dates >= pd.Timestamp(start)
    if end is not None:
        in_window &= dates <= pd.Timestamp(end)

    has_outcome = ctx.forward[fwd_col].reindex(dates).notna().to_numpy()
    valid_idx = np.where(in_window & has_outcome)[0]
    if stride > 1:
        valid_idx = valid_idx[::stride]

    rows: list[BacktestRow] = []
    for n, i in enumerate(valid_idx):
        t = dates[i]
        d = decide(ctx, query_date=t, primary_horizon=horizon, top_n=top_n)
        actual = float(ctx.forward.at[t, fwd_col])

        contribs = {c.name: c.contribution for c in d.score.components}
        rows.append(
            BacktestRow(
                date=t,
                horizon=horizon,
                p_up=d.score.p_up,
                p_up_raw=d.score.p_up_raw,
                p_down=d.score.p_down,
                bias=d.score.bias,
                confidence=d.score.confidence,
                calibrated=d.score.calibrated,
                expected_logret=d.score.expected_logret,
                expected_realvol=d.score.expected_realvol,
                sample_size=d.score.sample_size,
                effective_sample_size=d.score.effective_sample_size,
                contrib_astro=contribs.get("astro", 0.0),
                contrib_market=contribs.get("market", 0.0),
                contrib_regime=contribs.get("regime", 0.0),
                actual_logret=actual,
                actual_up=int(actual > 0),
            )
        )
        if progress_callback is not None:
            progress_callback(n + 1, len(valid_idx))

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([r.__dict__ for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df
