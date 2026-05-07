"""Central configuration. Single source of truth for paths, horizons, feature weights."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data_cache"
CACHE_DIR.mkdir(exist_ok=True)


@dataclass(frozen=True)
class Horizons:
    """Forward-return horizons (in trading days) used everywhere outcomes are aggregated."""

    days: tuple[int, ...] = (1, 3, 5, 10, 21, 63)


@dataclass(frozen=True)
class FeatureGroups:
    """Feature-group weights used by the similarity engine.

    These are deliberately exposed: the confluence layer decomposes the final score
    by group, so the user always sees how astro vs. market vs. regime contributed.
    """

    astro: float = 0.40
    market: float = 0.35
    regime: float = 0.25

    def normalized(self) -> dict[str, float]:
        s = self.astro + self.market + self.regime
        return {"astro": self.astro / s, "market": self.market / s, "regime": self.regime / s}


@dataclass(frozen=True)
class SimilarityConfig:
    top_n: int = 50
    metric: str = "cosine"  # cosine | euclidean
    min_lookback_days: int = 252  # never match against the most recent year (avoid leakage)
    decay_half_life_years: float = 8.0  # older matches get less weight


@dataclass(frozen=True)
class Settings:
    horizons: Horizons = field(default_factory=Horizons)
    feature_groups: FeatureGroups = field(default_factory=FeatureGroups)
    similarity: SimilarityConfig = field(default_factory=SimilarityConfig)
    cache_dir: Path = CACHE_DIR
    default_symbol: str = "SPY"
    default_history_start: str = "1995-01-01"


SETTINGS = Settings()
