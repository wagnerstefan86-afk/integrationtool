FROM python:3.11-slim

LABEL maintainer="InfoSec DE/AT" \
      description="Harmonizer - InfoSec Process Harmonization Analysis Tool"

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Build-time args for version tracing
ARG APP_VERSION=0.9.0
ARG GIT_COMMIT=unknown
ARG BUILD_DATE=unknown

# Bake version info into the image
ENV APP_VERSION=${APP_VERSION} \
    GIT_COMMIT=${GIT_COMMIT} \
    BUILD_DATE=${BUILD_DATE}

WORKDIR /app

# Install system dependencies (git for commit tracing in dev)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml /app/
COPY src/ /app/src/
COPY data/examples/ /data/examples/

# Install the package
RUN pip install --no-cache-dir -e ".[dev]"

# Create directory structure for persistent data
RUN mkdir -p /data/examples /data/pilot \
             /reports/generated /reports/reviewed \
             /logs

# Expose API port
EXPOSE 8001

# Health check — verify API responds with status ok
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, json; d=json.loads(urllib.request.urlopen('http://localhost:8001/health').read()); assert d['status']=='ok'" || exit 1

# Entrypoint: uvicorn serving the FastAPI app
CMD ["uvicorn", "harmonizer.api:app", "--host", "0.0.0.0", "--port", "8001", "--log-level", "info"]
