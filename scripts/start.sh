#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Harmonizer — Startup Script
# Pre-flight checks, seed data setup, and docker-compose up.
#
# Usage:
#   ./scripts/start.sh          # build and start
#   ./scripts/start.sh --build  # force rebuild images
#   ./scripts/start.sh --stop   # stop all services
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# ─── Parse args ───────────────────────────────────────────────
ACTION="start"
BUILD_FLAG=""
for arg in "$@"; do
    case "$arg" in
        --build)  BUILD_FLAG="--build" ;;
        --stop)   ACTION="stop" ;;
        --help|-h)
            echo "Usage: $0 [--build] [--stop]"
            echo "  --build   Force rebuild Docker images"
            echo "  --stop    Stop all services"
            exit 0
            ;;
    esac
done

# ─── Stop ─────────────────────────────────────────────────────
if [ "$ACTION" = "stop" ]; then
    echo "Stopping Harmonizer..."
    docker compose down
    echo "Stopped."
    exit 0
fi

echo "═══════════════════════════════════════════════════"
echo "  Harmonizer — Startup"
echo "═══════════════════════════════════════════════════"

# ─── Pre-flight: Docker ──────────────────────────────────────
echo "[1/5] Checking Docker..."
if ! command -v docker &>/dev/null; then
    echo "ERROR: docker not found. Install Docker >= 20.10"
    exit 1
fi
if ! docker info &>/dev/null; then
    echo "ERROR: Docker daemon not running."
    exit 1
fi
echo "  OK: $(docker --version)"

# ─── Pre-flight: .env ────────────────────────────────────────
echo "[2/5] Checking configuration..."
if [ ! -f .env ]; then
    echo "  .env not found — copying from .env.example"
    cp .env.example .env
fi
set -a
# shellcheck source=/dev/null
source .env
set +a
echo "  OK: .env loaded"

# ─── Pre-flight: directories ─────────────────────────────────
echo "[3/5] Ensuring directory structure..."
DATA_PATH="${DATA_PATH:-./deploy/data}"
REPORT_PATH="${REPORT_PATH:-./deploy/reports}"
LOG_PATH="${LOG_PATH:-./deploy/logs}"

for dir in \
    "$DATA_PATH/examples" \
    "$DATA_PATH/pilot" \
    "$REPORT_PATH/generated" \
    "$REPORT_PATH/reviewed" \
    "$LOG_PATH"; do
    mkdir -p "$dir"
done
mkdir -p deploy/backups
echo "  OK: directories ready"

# ─── Pre-flight: seed data ───────────────────────────────────
echo "[4/5] Checking seed data..."
if [ ! -f "$DATA_PATH/examples/processes.yaml" ]; then
    if [ -f data/examples/processes.yaml ]; then
        echo "  Copying seed data to $DATA_PATH/examples/"
        cp data/examples/*.yaml "$DATA_PATH/examples/"
    else
        echo "  WARNING: No seed data found in data/examples/"
    fi
else
    echo "  OK: seed data present"
fi

# ─── Inject version info ─────────────────────────────────────
echo "[5/5] Setting version metadata..."
export APP_VERSION="${APP_VERSION:-0.9.0}"
export GIT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
export BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "  Version: $APP_VERSION"
echo "  Commit:  $GIT_COMMIT"
echo "  Built:   $BUILD_DATE"

# ─── Start ────────────────────────────────────────────────────
echo "───────────────────────────────────────────────────"
echo "Starting services..."
docker compose up -d $BUILD_FLAG

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Harmonizer is running"
echo "  Frontend: http://localhost:${FRONTEND_PORT:-3001}"
echo "  Backend:  http://localhost:${BACKEND_PORT:-8001}"
echo "  Health:   http://localhost:${BACKEND_PORT:-8001}/health"
echo "═══════════════════════════════════════════════════"
echo ""
echo "Commands:"
echo "  Logs:    docker compose logs -f"
echo "  Stop:    ./scripts/start.sh --stop"
echo "  Backup:  ./scripts/backup.sh"
