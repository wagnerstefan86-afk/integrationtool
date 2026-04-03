FROM python:3.11-slim

LABEL maintainer="InfoSec DE/AT" \
      description="Harmonizer - InfoSec Process Harmonization Analysis Tool"

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (git for commit tracing)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml /app/
COPY src/ /app/src/
COPY data/examples/ /data/examples/

# Install the package
RUN pip install --no-cache-dir -e ".[dev]"

# Create directory structure
RUN mkdir -p /data/examples /data/pilot /data/outcomes /data/archive \
             /reports/generated /reports/reviewed \
             /logs

# Expose API port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

# Entrypoint: uvicorn serving the FastAPI app
CMD ["uvicorn", "harmonizer.api:app", "--host", "0.0.0.0", "--port", "8001", "--log-level", "info"]
