"""Time-decay + regime-relevance weighting for similarity matches.

Each match m gets:
  w(m) = similarity(m)
       * exp(-age_years(m) / tau)        time decay
       * regime_kernel(m)                 down-weight if regime is alien

Output is normalized so weights sum to 1 (the OutcomeBundle does its own
normalization too — both work).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import SETTINGS
from ..similarity.engine import SimilarityResult


def compute_weights(
    result: SimilarityResult,
    half_life_years: float | None = None,
    regime_emphasis: float = 1.0,
) -> np.ndarray:
    """Return per-match weights aligned with result.matches order."""
    half_life = half_life_years or SETTINGS.similarity.decay_half_life_years
    tau = half_life / np.log(2)  # convert half-life to e-fold time

    sims = np.array([m.similarity for m in result.matches], dtype=np.float64)
    # Cosine sims can be negative; shift to [0, 1] for stability without flipping rank.
    sims = (sims + 1.0) / 2.0

    ages = np.array(
        [(result.query_date - m.date).days / 365.25 for m in result.matches], dtype=np.float64
    )
    decay = np.exp(-np.maximum(ages, 0.0) / tau)

    # Regime kernel: similarity restricted to regime features (already computed per match).
    regime_sim = np.array(
        [m.per_group_similarity.get("regime", 0.0) for m in result.matches], dtype=np.float64
    )
    regime_kernel = np.exp(regime_emphasis * (regime_sim - 1.0))  # in (0, 1], peaks at exact match

    w = sims * decay * regime_kernel
    s = w.sum()
    if s <= 0:
        return np.full_like(w, 1.0 / max(len(w), 1))
    return w / s
