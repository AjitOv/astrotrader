"""Backtest harness tests. Reuses the session-scope ctx from test_smoke."""
from __future__ import annotations

import numpy as np
import pandas as pd

from astrotrader.backtest.metrics import (
    brier_score,
    expected_calibration_error,
    log_loss,
    naive_strategy_equity,
    reliability_table,
)
from astrotrader.backtest.report import summarize
from astrotrader.backtest.walk_forward import walk_forward


def test_metrics_perfect_predictor() -> None:
    """Metrics should give floor values for a perfectly-calibrated oracle."""
    p = np.array([1.0, 0.0, 1.0, 0.0])
    y = np.array([1, 0, 1, 0])
    assert brier_score(p, y) == 0.0
    assert log_loss(p, y) < 1e-6
    assert expected_calibration_error(p, y) == 0.0


def test_metrics_random_predictor() -> None:
    rng = np.random.default_rng(0)
    p = np.full(1000, 0.5)
    y = rng.integers(0, 2, size=1000)
    assert abs(brier_score(p, y) - 0.25) < 0.05
    assert abs(log_loss(p, y) - 0.693) < 0.05


def test_walk_forward_produces_rows(ctx) -> None:  # uses fixture from test_smoke
    rows = walk_forward(
        ctx,
        horizon=5,
        start="2024-06-01",
        end="2024-09-30",
        top_n=20,
        stride=5,
    )
    assert not rows.empty
    assert {"date", "p_up", "actual_logret", "actual_up", "bias"}.issubset(rows.columns)
    # Probabilities are bounded
    assert (rows["p_up"] >= 0).all() and (rows["p_up"] <= 1).all()
    assert rows["actual_up"].isin([0, 1]).all()
    # Predicted distribution is non-degenerate (not all the same value)
    assert rows["p_up"].nunique() > 1


def test_summary_runs(ctx) -> None:
    rows = walk_forward(ctx, horizon=5, start="2024-06-01", end="2024-09-30", top_n=20, stride=5)
    s = summarize(rows, horizon=5, confidence_threshold=0.0)
    assert s.n == len(rows)
    assert 0.0 <= s.brier <= 1.0
    assert s.log_loss > 0.0
    assert 0.0 <= s.ece <= 1.0
    assert not s.equity.empty
    assert "total_logret" in s.strategy


def test_strategy_equity_no_position_no_pnl() -> None:
    """When confidence threshold excludes everything, strategy equity stays at 1.0."""
    rows = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=5),
            "p_up": [0.5] * 5,
            "p_down": [0.5] * 5,
            "bias": ["neutral"] * 5,
            "confidence": [0.0] * 5,
            "actual_logret": [0.01, -0.01, 0.005, -0.005, 0.0],
        }
    )
    eq = naive_strategy_equity(rows, confidence_threshold=0.5)
    # No active positions → all pnl == 0 → equity stays at 1.
    assert np.allclose(eq["equity"].to_numpy(), 1.0)


def test_reliability_columns_only_for_populated_bins() -> None:
    p = np.array([0.05, 0.15, 0.95])
    y = np.array([0, 0, 1])
    rt = reliability_table(p, y, n_bins=10)
    # Only bins 0, 1, 9 should appear
    assert len(rt) == 3
    assert {"bin_low", "bin_high", "n", "mean_predicted", "mean_actual"} == set(rt.columns)
