"""Shared pytest fixtures."""
from __future__ import annotations

import pytest

from astrotrader.pipeline import AstrotradeContext


@pytest.fixture(scope="session")
def ctx() -> AstrotradeContext:
    # Short window keeps the cold-cache test pass under ~30s; once the parquet
    # cache exists, every subsequent run is sub-second.
    return AstrotradeContext.build(symbol="SPY", start="2005-01-01")
