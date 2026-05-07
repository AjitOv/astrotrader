"""FastAPI surface. Per-symbol AstrotradeContext is built lazily and cached
in memory — first request warms it, subsequent requests are O(N×D) for query.

Pre-warming: a small set of popular symbols is built in a background thread
during startup so common loads are instant. Anything not pre-warmed is built
on first request — slow (~5–10s) but happens only once per server lifetime.

Run: uvicorn astrotrader.api.main:app --port 8000
"""
from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import asdict
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..calibration.calibrator import auto_load
from ..pipeline import AstrotradeContext, decide

log = logging.getLogger("astrotrader.api")

# Configurable at deploy time. On Render free tier (512 MB RAM) we keep this
# tight; locally the default warms five symbols. Comma-separated env var.
WARMUP_SYMBOLS = [
    s.strip().upper()
    for s in os.environ.get("ASTROTRADE_WARMUP", "SPY,QQQ,NIFTY,BTCUSD,GLD").split(",")
    if s.strip()
]

# Comma-separated origins; "*" allowed for permissive deployments.
_cors_env = os.environ.get(
    "ASTROTRADE_CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001",
)
CORS_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()]

DEFAULT_HORIZONS_TO_LOAD_CALIBRATORS = (5,)

_CTX_CACHE: dict[str, AstrotradeContext] = {}
_BUILDING: dict[str, asyncio.Event] = {}
_LOCK = Lock()


def _build_and_cache(symbol: str) -> AstrotradeContext:
    """Build a fresh context, attach any saved calibrators, store in cache."""
    ctx = AstrotradeContext.build(symbol=symbol)
    for h in DEFAULT_HORIZONS_TO_LOAD_CALIBRATORS:
        cal = auto_load(symbol, h)
        if cal is not None:
            ctx = ctx.attach_calibrator(cal)
    with _LOCK:
        _CTX_CACHE[symbol] = ctx
    return ctx


def _get_ctx(symbol: str) -> AstrotradeContext:
    """Synchronous get — used inside the threadpool. Builds on miss."""
    symbol = symbol.upper()
    with _LOCK:
        cached = _CTX_CACHE.get(symbol)
    if cached is not None:
        return cached
    log.info("building context for %s on demand", symbol)
    return _build_and_cache(symbol)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Spawn a background warmup task. We don't await it — the server should
    start serving immediately, even if warmup is still going."""
    loop = asyncio.get_event_loop()
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="astro-warm")

    async def warm_one(sym: str):
        with _LOCK:
            if sym in _CTX_CACHE:
                return
        try:
            await loop.run_in_executor(pool, _build_and_cache, sym)
            log.info("warmed %s", sym)
        except Exception as e:  # warmup must never crash the server
            log.warning("warm %s failed: %s", sym, e)

    async def warm_all():
        for sym in WARMUP_SYMBOLS:
            await warm_one(sym)

    asyncio.create_task(warm_all())
    yield
    pool.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="ASTROTRADE", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class DecideRequest(BaseModel):
    symbol: str = "SPY"
    horizon: int = 5
    date: str | None = None
    top_n: int | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/decide")
def decide_endpoint(req: DecideRequest) -> dict:
    try:
        ctx = _get_ctx(req.symbol)
        decision = decide(
            ctx,
            query_date=req.date,
            primary_horizon=req.horizon,
            top_n=req.top_n,
        )
    except Exception as e:  # surface as 400 — the input space is small
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Pull the ephemeris row at the query date for the radial Clock.
    pos_row = ctx.positions.loc[decision.query_date]
    bodies = [
        "sun", "moon", "mercury", "venus", "mars",
        "jupiter", "saturn", "uranus", "neptune", "pluto",
    ]
    ephemeris = {
        b: {
            "longitude": float(pos_row[f"{b}_lon"]),
            "speed": float(pos_row[f"{b}_speed"]),
            "retrograde": bool(pos_row[f"{b}_speed"] < 0) if b not in ("sun", "moon") else False,
        }
        for b in bodies
    }

    # Recent SPY context for the Probability Field — last 60 trading days.
    px = ctx.prices.loc[ctx.prices.index <= decision.query_date].tail(60)
    recent_prices = [
        {"date": str(d.date()), "close": float(c)}
        for d, c in zip(px.index, px["close"].values)
    ]

    return {
        "symbol": req.symbol.upper(),
        "query_date": str(decision.query_date.date()),
        "score": asdict(decision.score),
        "horizons": [asdict(h) for h in decision.bundle.horizons],
        "matches": [
            {
                "date": str(m.date.date()),
                "similarity": m.similarity,
                "per_group": m.per_group_similarity,
            }
            for m in decision.similarity.matches
        ],
        "ephemeris": ephemeris,
        "recent_prices": recent_prices,
    }


@app.get("/mirror/{symbol}")
def mirror(symbol: str, n: int = 10, date: str | None = None) -> dict:
    """Just the top-N most similar past dates for the given symbol."""
    ctx = _get_ctx(symbol)
    decision = decide(ctx, query_date=date, top_n=n)
    return {
        "symbol": symbol.upper(),
        "query_date": str(decision.query_date.date()),
        "matches": [
            {
                "date": str(m.date.date()),
                "similarity": m.similarity,
                "per_group": m.per_group_similarity,
            }
            for m in decision.similarity.matches
        ],
    }
