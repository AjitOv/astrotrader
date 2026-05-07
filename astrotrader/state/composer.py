"""STATE composer. Assembles astro + market + regime features into the canonical
high-dimensional STATE(t) vector and tracks which columns belong to which group
(so the similarity / confluence layers can decompose contributions).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import SETTINGS
from .astro import encode_astro
from .market import encode_market
from .regime import encode_regime


@dataclass
class StateMatrix:
    """Holds the historical state matrix and metadata needed to query it."""

    raw: pd.DataFrame              # un-normalized feature DataFrame, indexed by date
    matrix: np.ndarray             # (n_dates, n_features) z-scored
    columns: list[str]
    group_of: dict[str, str]       # column name -> "astro" | "market" | "regime"
    means: np.ndarray              # per-column training means
    stds: np.ndarray               # per-column training stds (clipped to avoid div-by-0)
    dates: pd.DatetimeIndex

    def group_indices(self) -> dict[str, np.ndarray]:
        groups: dict[str, list[int]] = {"astro": [], "market": [], "regime": []}
        for i, c in enumerate(self.columns):
            groups[self.group_of[c]].append(i)
        return {k: np.asarray(v, dtype=np.int64) for k, v in groups.items()}


def _classify(col: str) -> str:
    if col.startswith("astro_") or col.startswith("asp_"):
        return "astro"
    if col.startswith("mkt_"):
        return "market"
    if col.startswith("reg_"):
        return "regime"
    raise ValueError(f"unknown feature group for column {col!r}")


def _z_score(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Column-wise z-score with NaN-safe stats. Returns (z, means, stds)."""
    arr = df.to_numpy(dtype=np.float64, copy=True)
    means = np.nanmean(arr, axis=0)
    stds = np.nanstd(arr, axis=0)
    stds = np.where(stds < 1e-9, 1.0, stds)
    z = (arr - means) / stds
    # Replace residual NaNs with 0 — they'll be near the mean after z-scoring.
    z = np.nan_to_num(z, nan=0.0, posinf=0.0, neginf=0.0)
    return z, means, stds


def compose(
    prices: pd.DataFrame,
    positions: pd.DataFrame,
    drop_warmup: int = 252,
) -> StateMatrix:
    """Build a StateMatrix from already-loaded prices + ephemeris positions.

    drop_warmup trims rows before rolling windows have stabilized.
    """
    astro = encode_astro(positions)
    market = encode_market(prices)
    regime = encode_regime(prices)

    # Align all three on the intersection of indexes — yfinance gives trading days,
    # ephemeris gives whatever dates we passed in (we'll pass trading days).
    common_idx = astro.index.intersection(market.index).intersection(regime.index)
    astro = astro.loc[common_idx]
    market = market.loc[common_idx]
    regime = regime.loc[common_idx]

    raw = pd.concat([astro, market, regime], axis=1)
    if drop_warmup:
        raw = raw.iloc[drop_warmup:]

    # Drop rows that still have NaNs after warmup (rare; safety net).
    raw = raw.dropna(how="any")

    z, means, stds = _z_score(raw)
    columns = list(raw.columns)
    group_of = {c: _classify(c) for c in columns}

    return StateMatrix(
        raw=raw,
        matrix=z,
        columns=columns,
        group_of=group_of,
        means=means,
        stds=stds,
        dates=raw.index,
    )


def normalize_query(query_raw: pd.Series, sm: StateMatrix) -> np.ndarray:
    """Project a single raw row into the same z-scored space as the matrix.

    Used when scoring a brand-new STATE(t) (e.g. today) against history.
    """
    arr = query_raw.reindex(sm.columns).to_numpy(dtype=np.float64)
    z = (arr - sm.means) / sm.stds
    return np.nan_to_num(z, nan=0.0, posinf=0.0, neginf=0.0)


def feature_group_weights() -> dict[str, float]:
    """Re-export normalized group weights for the similarity engine."""
    return SETTINGS.feature_groups.normalized()
