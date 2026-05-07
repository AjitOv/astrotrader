"""Similarity engine.

Given a query STATE vector, find the K nearest historical states under a
group-weighted distance, and return both the matches AND the per-group
breakdown so the UI can show *why* something looked similar.

Design notes
------------
* We pre-scale each column by sqrt(group_weight / group_size) so the L2 distance
  on the scaled matrix is identical to the weighted-group distance — no
  per-group loops at query time. Cosine works the same way.
* "Why was this date similar?" is answered by re-computing per-group similarity
  on the unscaled vectors for just the top-N matches. Cheap because N is small.
* The min_lookback_days guard prevents matching against the trailing window
  that contains the query itself (data leakage).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import SETTINGS
from ..state.composer import StateMatrix, feature_group_weights


@dataclass
class Match:
    date: pd.Timestamp
    similarity: float
    per_group_similarity: dict[str, float]
    row_index: int  # position in the StateMatrix


@dataclass
class SimilarityResult:
    query_date: pd.Timestamp
    matches: list[Match]
    metric: str

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": [m.date for m in self.matches],
                "similarity": [m.similarity for m in self.matches],
                **{
                    f"sim_{g}": [m.per_group_similarity.get(g, 0.0) for m in self.matches]
                    for g in ("astro", "market", "regime")
                },
            }
        )


class SimilarityEngine:
    """Group-weighted similarity over a StateMatrix."""

    def __init__(self, sm: StateMatrix, group_weights: dict[str, float] | None = None):
        self.sm = sm
        self.group_weights = group_weights or feature_group_weights()
        self._build_scaled_matrix()

    def _build_scaled_matrix(self) -> None:
        groups = self.sm.group_indices()
        scale = np.ones(self.sm.matrix.shape[1], dtype=np.float64)
        for g, idx in groups.items():
            if len(idx) == 0:
                continue
            # Per-feature scale so that ||scale*x||² over a group equals weight_g.
            # i.e. each column contributes weight_g / |group| to the squared norm.
            per = np.sqrt(self.group_weights[g] / len(idx))
            scale[idx] = per
        self.scale = scale
        self.scaled = self.sm.matrix * scale  # (N, D)
        norms = np.linalg.norm(self.scaled, axis=1)
        self.unit = self.scaled / np.where(norms < 1e-12, 1.0, norms)[:, None]
        self.norms = norms

    # ------------------------------------------------------------------ public

    def query(
        self,
        query_z: np.ndarray,
        query_date: pd.Timestamp,
        top_n: int | None = None,
        metric: str | None = None,
        min_lookback_days: int | None = None,
    ) -> SimilarityResult:
        cfg = SETTINGS.similarity
        top_n = top_n or cfg.top_n
        metric = metric or cfg.metric
        min_lookback_days = (
            min_lookback_days if min_lookback_days is not None else cfg.min_lookback_days
        )

        scaled_q = query_z * self.scale

        if metric == "cosine":
            qn = np.linalg.norm(scaled_q)
            unit_q = scaled_q / (qn if qn > 1e-12 else 1.0)
            sims = self.unit @ unit_q  # (N,)
        elif metric == "euclidean":
            d = self.scaled - scaled_q
            dist = np.linalg.norm(d, axis=1)
            # Convert to a similarity in (0, 1] for ranking convenience.
            sims = 1.0 / (1.0 + dist)
        else:
            raise ValueError(f"unknown metric {metric!r}")

        # Mask out the trailing window so we don't match against ourselves
        cutoff = query_date - pd.Timedelta(days=min_lookback_days)
        valid = self.sm.dates < cutoff
        sims = np.where(valid, sims, -np.inf)

        order = np.argpartition(-sims, min(top_n, len(sims) - 1))[:top_n]
        order = order[np.argsort(-sims[order])]

        # Per-group breakdown: cosine similarity on the un-scaled z vectors restricted
        # to each group's columns. This is the human-readable "why" panel.
        groups = self.sm.group_indices()
        matches: list[Match] = []
        for i in order:
            if not np.isfinite(sims[i]):
                break
            per_group = {}
            for g, idx in groups.items():
                v_hist = self.sm.matrix[i, idx]
                v_q = query_z[idx]
                nh = np.linalg.norm(v_hist)
                nq = np.linalg.norm(v_q)
                if nh < 1e-12 or nq < 1e-12:
                    per_group[g] = 0.0
                else:
                    per_group[g] = float(v_hist @ v_q / (nh * nq))
            matches.append(
                Match(
                    date=self.sm.dates[i],
                    similarity=float(sims[i]),
                    per_group_similarity=per_group,
                    row_index=int(i),
                )
            )

        return SimilarityResult(query_date=query_date, matches=matches, metric=metric)
