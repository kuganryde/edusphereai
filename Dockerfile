# syntax=docker/dockerfile:1

# ---- Builder ----------------------------------------------------------
# Resolves and installs dependencies into a venv. Kept separate from the
# runtime stage so the final image doesn't carry uv, build tools, or pip
# caches.
FROM python:3.12-slim AS builder

# Official static uv binary — no network call needed inside the build.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# Install deps first (better layer caching: this layer only invalidates
# when pyproject.toml/uv.lock change, not on every code edit). `package =
# false` in pyproject.toml means there's no local project install step, so
# this alone fully populates the venv — no second `uv sync` is needed (or
# wanted) after the app code is copied in below.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Swap in the CPU-only PyTorch build — the default resolution pulls the
# CUDA-bundled wheel from PyPI (~5GB) even though containers here run on
# CPU. Same code, a few hundred MB instead of several gigabytes. See
# README "Lightweight / CPU-only install" for the rationale. This must be
# the last dependency-touching step: a later `uv sync --frozen` would
# reinstall the CUDA build to match uv.lock and undo this swap.
RUN uv pip install --python /app/.venv/bin/python \
    torch --index-url https://download.pytorch.org/whl/cpu --reinstall

# ---- Runtime ------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Minimal system libs opencv-python-headless needs even without GUI support.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 sentryvision
WORKDIR /app

COPY --from=builder --chown=sentryvision:sentryvision /app/.venv /app/.venv
COPY --chown=sentryvision:sentryvision . .

# Runtime data (SQLite DB, snapshots, downloaded model weights, zones/settings
# JSON) — mount a volume here to persist across container restarts.
RUN mkdir -p /app/data/snapshots /app/data/models \
    && chown -R sentryvision:sentryvision /app/data
VOLUME ["/app/data"]

USER sentryvision
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

ENTRYPOINT ["streamlit", "run", "streamlit_app.py", \
    "--server.address=0.0.0.0", \
    "--server.port=8501", \
    "--server.headless=true"]
