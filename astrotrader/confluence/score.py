"""Confluence scoring layer — turns the outcome bundle + per-group similarity
into a decomposable, decision-grade score.

Decomposition method
--------------------
The "contribution" of each feature group is the marginal shift in P(up) that
group's similarity creates relative to a uniform baseline:

    p_group  = sum_i (w_i^group * 1[ret_i > 0]) / sum_i w_i^group
    p_unif   = mean_i 1[ret_i > 0]
    contrib  = p_group - p_unif

In English: "If we re-rank history by astro-similarity alone, does the up-rate
go up or down?" Same question, three groups. Sums approximately to (p_full − p_unif)
when groups are roughly orthogonal.

NEVER outputs certainty. Always outputs a probability + the contributing parts.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..calibration.calibrator import Calibrator
from ..outcomes.distribution import OutcomeBundle
from ..similarity.engine import SimilarityResult


@dataclass
class ScoreComponent:
    name: str
    contribution: float          # probability points, signed
    detail: str = ""


@dataclass
class ConfluenceScore:
    horizon: int
    bias: str                    # "bullish" | "bearish" | "neutral"
    p_up: float                  # calibrated if a calibrator was supplied; else == p_up_raw
    p_up_raw: float              # always the uncalibrated bundle weighted-vote p_up
    p_down: float                # 1 − p_up after calibration; sample weight otherwise
    confidence: float            # in [0, 1]
    expected_logret: float
    expected_realvol: float
    calibrated: bool = False     # True if a calibrator was applied
    components: list[ScoreComponent] = field(default_factory=list)
    sample_size: int = 0
    effective_sample_size: float = 0.0


def _label(p_up: float, threshold: float = 0.55) -> str:
    if p_up >= threshold:
        return "bullish"
    if p_up <= 1 - threshold:
        return "bearish"
    return "neutral"


def _ess_confidence(ess: float, target: float = 30.0) -> float:
    return float(1.0 / (1.0 + np.exp(-(ess - target) / (target / 4))))


def score(
    bundle: OutcomeBundle,
    result: SimilarityResult,
    forward: pd.DataFrame,
    primary_horizon: int = 5,
    calibrator: Calibrator | None = None,
) -> ConfluenceScore:
    h_outcome = next((h for h in bundle.horizons if h.horizon == primary_horizon), None)
    if h_outcome is None:
        if not bundle.horizons:
            return ConfluenceScore(
                horizon=primary_horizon,
                bias="neutral",
                p_up=0.5,
                p_up_raw=0.5,
                p_down=0.5,
                confidence=0.0,
                expected_logret=0.0,
                expected_realvol=0.0,
                sample_size=0,
            )
        h_outcome = bundle.horizons[0]
        primary_horizon = h_outcome.horizon

    # Build the aligned forward-return vector for the matched dates.
    col = f"fwd_logret_{primary_horizon}"
    rets = np.array(
        [float(forward.at[m.date, col]) if m.date in forward.index else np.nan
         for m in result.matches],
        dtype=np.float64,
    )
    valid = np.isfinite(rets)

    p_unif = float(np.mean(rets[valid] > 0)) if valid.any() else 0.5

    components: list[ScoreComponent] = []
    for group in ("astro", "market", "regime"):
        g_sims = np.array(
            [(m.per_group_similarity.get(group, 0.0) + 1) / 2 for m in result.matches],
            dtype=np.float64,
        )
        g_sims = g_sims[valid]
        r = rets[valid]
        denom = g_sims.sum()
        p_group = float(np.sum(g_sims * (r > 0).astype(float)) / denom) if denom > 0 else p_unif
        contrib = (p_group - p_unif) * 100.0
        components.append(
            ScoreComponent(name=group, contribution=contrib, detail=f"p_{group}={p_group:.3f}")
        )

    p_up_raw = h_outcome.p_up
    if calibrator is not None:
        p_up = float(calibrator.transform(np.array([p_up_raw]))[0])
        p_down = 1.0 - p_up
        calibrated = True
    else:
        p_up = p_up_raw
        p_down = h_outcome.p_down
        calibrated = False
    confidence = _ess_confidence(bundle.effective_sample_size) * (abs(p_up - 0.5) * 2.0)

    return ConfluenceScore(
        horizon=h_outcome.horizon,
        bias=_label(p_up),
        p_up=p_up,
        p_up_raw=p_up_raw,
        p_down=p_down,
        confidence=confidence,
        expected_logret=h_outcome.mean_logret,
        expected_realvol=h_outcome.expected_realvol,
        calibrated=calibrated,
        components=components,
        sample_size=bundle.sample_size,
        effective_sample_size=bundle.effective_sample_size,
    )
