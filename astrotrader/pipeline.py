"""End-to-end pipeline: load data → build STATE matrix → query → score.

This is the only module that wires all the engines together. Everything else
is single-responsibility and reusable.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import pandas as pd

from .calibration.calibrator import Calibrator
from .confluence.score import ConfluenceScore, score as confluence_score
from .data.ephemeris import cached_positions
from .data.prices import load_prices
from .decay.weights import compute_weights
from .outcomes.distribution import OutcomeBundle, aggregate
from .outcomes.forward import compute_forward
from .similarity.engine import SimilarityEngine, SimilarityResult
from .state.composer import StateMatrix, compose


@dataclass
class AstrotradeContext:
    """Pre-built artifacts for repeated queries on a single symbol."""

    symbol: str
    prices: pd.DataFrame
    positions: pd.DataFrame
    state_matrix: StateMatrix
    forward: pd.DataFrame
    engine: SimilarityEngine
    calibrators: dict[int, Calibrator] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        symbol: str = "SPY",
        start: str | None = None,
        end: str | None = None,
        refresh: bool = False,
    ) -> "AstrotradeContext":
        prices = load_prices(symbol=symbol, start=start, end=end, refresh=refresh)
        positions = cached_positions(prices.index, symbol_tag=symbol)
        state_matrix = compose(prices, positions)
        forward = compute_forward(prices)
        engine = SimilarityEngine(state_matrix)
        return cls(
            symbol=symbol,
            prices=prices,
            positions=positions,
            state_matrix=state_matrix,
            forward=forward,
            engine=engine,
        )

    def attach_calibrator(self, calibrator: Calibrator) -> "AstrotradeContext":
        """Return a copy of this context with the given calibrator attached
        for its declared horizon. Existing calibrators for other horizons are kept."""
        new_cals = {**self.calibrators, calibrator.horizon: calibrator}
        return replace(self, calibrators=new_cals)


@dataclass
class Decision:
    query_date: pd.Timestamp
    primary_horizon: int
    score: ConfluenceScore
    bundle: OutcomeBundle
    similarity: SimilarityResult


def decide(
    ctx: AstrotradeContext,
    query_date: pd.Timestamp | str | None = None,
    primary_horizon: int = 5,
    top_n: int | None = None,
) -> Decision:
    if query_date is None:
        query_date = ctx.state_matrix.dates[-1]
    query_date = pd.Timestamp(query_date).normalize()

    # Locate query row (must exist in state matrix).
    if query_date not in ctx.state_matrix.dates:
        # nearest prior trading day
        idx = ctx.state_matrix.dates.searchsorted(query_date, side="right") - 1
        if idx < 0:
            raise ValueError(f"query date {query_date} is before any state we have")
        query_date = ctx.state_matrix.dates[idx]

    pos = ctx.state_matrix.dates.get_loc(query_date)
    query_z = ctx.state_matrix.matrix[pos]

    sim_result = ctx.engine.query(query_z, query_date, top_n=top_n)
    weights = compute_weights(sim_result)
    matched_dates = [m.date for m in sim_result.matches]
    bundle = aggregate(ctx.forward, matched_dates, weights)
    calibrator = ctx.calibrators.get(primary_horizon)
    s = confluence_score(
        bundle,
        sim_result,
        ctx.forward,
        primary_horizon=primary_horizon,
        calibrator=calibrator,
    )
    return Decision(
        query_date=query_date,
        primary_horizon=primary_horizon,
        score=s,
        bundle=bundle,
        similarity=sim_result,
    )
