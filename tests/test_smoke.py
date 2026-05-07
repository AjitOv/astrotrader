"""End-to-end smoke test. Pulls SPY from yfinance, builds STATE matrix, queries,
verifies shape and invariants."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from astrotrader.pipeline import AstrotradeContext, decide


def test_state_matrix_shape(ctx: AstrotradeContext) -> None:
    sm = ctx.state_matrix
    assert sm.matrix.ndim == 2
    n_rows, n_cols = sm.matrix.shape
    assert n_rows > 1000
    assert 50 <= n_cols <= 400, f"unexpected feature width: {n_cols}"
    assert len(sm.columns) == n_cols
    # Every column classified into a group
    assert set(sm.group_of.values()) <= {"astro", "market", "regime"}


def test_state_matrix_normalized(ctx: AstrotradeContext) -> None:
    z = ctx.state_matrix.matrix
    # Z-scored columns: per-column mean ≈ 0, std ≈ 1 (modulo NaN/edge effects)
    means = z.mean(axis=0)
    stds = z.std(axis=0)
    assert np.all(np.abs(means) < 1e-6)
    assert np.all(np.abs(stds - 1.0) < 1e-3)


def test_decide_runs(ctx: AstrotradeContext) -> None:
    d = decide(ctx, primary_horizon=5, top_n=50)
    s = d.score
    assert 0.0 <= s.p_up <= 1.0
    assert 0.0 <= s.p_down <= 1.0
    # p_up + p_down may be < 1 if any neutral days (ret == 0). Sanity: sum ≤ 1.
    assert s.p_up + s.p_down <= 1.0 + 1e-6
    assert s.bias in {"bullish", "bearish", "neutral"}
    assert s.sample_size > 0
    assert math.isfinite(s.expected_logret)
    assert len(d.similarity.matches) > 0
    # Per-group similarities are bounded cosines
    for m in d.similarity.matches:
        for v in m.per_group_similarity.values():
            assert -1.001 <= v <= 1.001
    # At least one component has a non-zero contribution
    assert any(abs(c.contribution) > 1e-9 for c in s.components)


def test_no_lookahead(ctx: AstrotradeContext) -> None:
    """Matches must be older than the query date by at least min_lookback_days."""
    from astrotrader.config import SETTINGS
    qd = ctx.state_matrix.dates[-1]
    d = decide(ctx, query_date=qd, top_n=20)
    cutoff = qd - pd.Timedelta(days=SETTINGS.similarity.min_lookback_days)
    for m in d.similarity.matches:
        assert m.date < cutoff, f"match {m.date} violates lookback cutoff {cutoff}"
