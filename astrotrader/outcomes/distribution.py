"""Aggregate the forward outcomes of similar past states into a distribution."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import SETTINGS


@dataclass
class HorizonOutcome:
    horizon: int
    n: int
    weighted_n: float
    mean_logret: float
    median_logret: float
    std_logret: float
    p_up: float
    p_down: float
    quantiles: dict[str, float]   # "q05", "q25", "q50", "q75", "q95"
    expected_maxdd: float
    expected_maxup: float
    expected_realvol: float


@dataclass
class OutcomeBundle:
    horizons: list[HorizonOutcome] = field(default_factory=list)
    sample_size: int = 0
    effective_sample_size: float = 0.0  # Kish ESS — discounts heavy weighting
    historical_dates: list[pd.Timestamp] = field(default_factory=list)


def _kish_ess(weights: np.ndarray) -> float:
    s = float(np.sum(weights))
    s2 = float(np.sum(weights ** 2))
    return s * s / s2 if s2 > 0 else 0.0


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    """Type-7-ish weighted quantile."""
    if len(values) == 0:
        return float("nan")
    order = np.argsort(values)
    v = values[order]
    w = weights[order]
    cw = np.cumsum(w)
    cutoff = q * cw[-1]
    idx = np.searchsorted(cw, cutoff)
    return float(v[min(idx, len(v) - 1)])


def aggregate(
    forward: pd.DataFrame,
    matched_dates: list[pd.Timestamp],
    weights: np.ndarray,
    horizons: tuple[int, ...] | None = None,
) -> OutcomeBundle:
    """Build OutcomeBundle from forward returns indexed at the matched dates."""
    horizons = horizons or SETTINGS.horizons.days
    bundle = OutcomeBundle(historical_dates=list(matched_dates))

    if not matched_dates:
        return bundle

    # Pull the forward rows for the matched dates that exist in the forward frame.
    valid_mask = forward.index.isin(matched_dates)
    sub = forward.loc[valid_mask]
    # Re-align weights to match the subset, preserving original ordering.
    date_to_w = dict(zip(matched_dates, weights))
    w_sub = np.array([date_to_w[d] for d in sub.index], dtype=np.float64)

    bundle.sample_size = len(sub)
    bundle.effective_sample_size = _kish_ess(w_sub)

    for h in horizons:
        col = f"fwd_logret_{h}"
        if col not in sub.columns:
            continue
        rets = sub[col].to_numpy()
        finite = np.isfinite(rets)
        r = rets[finite]
        w = w_sub[finite]
        if len(r) == 0:
            continue
        wnorm = w / w.sum()

        mean = float(np.sum(r * wnorm))
        # Weighted variance
        var = float(np.sum(wnorm * (r - mean) ** 2))
        std = float(np.sqrt(max(var, 0.0)))

        p_up = float(np.sum(wnorm[r > 0]))
        p_down = float(np.sum(wnorm[r < 0]))

        quantiles = {
            f"q{int(q * 100):02d}": _weighted_quantile(r, w, q)
            for q in (0.05, 0.25, 0.50, 0.75, 0.95)
        }

        dd = sub[f"fwd_maxdd_{h}"].to_numpy()[finite]
        up = sub[f"fwd_maxup_{h}"].to_numpy()[finite]
        rv = sub[f"fwd_realvol_{h}"].to_numpy()[finite]

        def _wmean(x):
            mask = np.isfinite(x)
            if not mask.any():
                return float("nan")
            xn = x[mask]
            wn = w[mask]
            return float(np.sum(xn * wn) / np.sum(wn))

        bundle.horizons.append(
            HorizonOutcome(
                horizon=h,
                n=int(finite.sum()),
                weighted_n=float(w.sum()),
                mean_logret=mean,
                median_logret=quantiles["q50"],
                std_logret=std,
                p_up=p_up,
                p_down=p_down,
                quantiles=quantiles,
                expected_maxdd=_wmean(dd),
                expected_maxup=_wmean(up),
                expected_realvol=_wmean(rv),
            )
        )

    return bundle
