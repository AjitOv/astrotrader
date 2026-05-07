# ASTROTRADE engine — multi-stage build to keep the runtime image small.
# Render free tier has 512 MB RAM and ephemeral disk; we bake the JPL ephemeris
# kernel into the image so cold starts don't have to re-download 30 MB of bsp.
#
# Build:  docker build -t astrotrader .
# Run:    docker run -p 8000:8000 -e ASTROTRADE_CORS_ORIGINS="*" astrotrader
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install build deps for scipy / scikit-learn wheels on slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc g++ \
 && rm -rf /var/lib/apt/lists/*

# ----- deps layer (cached unless pyproject.toml changes) -----
COPY pyproject.toml ./
RUN pip install --upgrade pip \
 && pip install \
        "numpy>=1.26" "pandas>=2.1" "scipy>=1.11" "scikit-learn>=1.4" \
        "skyfield>=1.49" "yfinance>=0.2.40" "fastapi>=0.110" \
        "uvicorn[standard]>=0.29" "pydantic>=2.6" "python-dateutil>=2.8" \
        "joblib>=1.3" "click>=8.1" "pyarrow>=15.0"

# ----- code layer -----
COPY astrotrader/ ./astrotrader/
COPY data_cache/calibrator_*.joblib ./data_cache/

# ----- bake ephemeris kernel into the image -----
# Without this, the first request after every cold start would download 30 MB.
RUN python -c "from skyfield.api import Loader; \
              loader = Loader('./data_cache'); \
              loader('de440s.bsp')"

ENV PORT=8000
EXPOSE 8000

# Render injects $PORT; honor it. Single worker — context cache is in-process
# memory; multiple workers would each hold their own copy and break the warm cache.
CMD ["sh", "-c", "uvicorn astrotrader.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
