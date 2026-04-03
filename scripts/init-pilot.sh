#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Harmonizer — Initialize Pilot Dataset
# Creates a clean pilot data directory with empty structure files,
# optionally seeded from the example data.
#
# Usage:
#   ./scripts/init-pilot.sh                  # empty pilot dataset
#   ./scripts/init-pilot.sh --from-examples  # copy example structure
#   ./scripts/init-pilot.sh my_pilot         # custom dataset name
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load .env if present
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$PROJECT_DIR/.env"
    set +a
fi

DATA_PATH="${DATA_PATH:-$PROJECT_DIR/deploy/data}"
DATASET_NAME="pilot"
FROM_EXAMPLES=false

for arg in "$@"; do
    case "$arg" in
        --from-examples) FROM_EXAMPLES=true ;;
        --help|-h)
            echo "Usage: $0 [dataset_name] [--from-examples]"
            echo "  dataset_name     Name of the dataset (default: pilot)"
            echo "  --from-examples  Copy process structure from examples"
            exit 0
            ;;
        *) DATASET_NAME="$arg" ;;
    esac
done

PILOT_DIR="$DATA_PATH/$DATASET_NAME"

echo "═══════════════════════════════════════════════════"
echo "  Initialize Pilot Dataset: $DATASET_NAME"
echo "═══════════════════════════════════════════════════"
echo "  Target: $PILOT_DIR"

if [ -f "$PILOT_DIR/processes.yaml" ]; then
    echo ""
    echo "WARNING: $PILOT_DIR/processes.yaml already exists."
    read -rp "Overwrite? [y/N] " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "Aborted."
        exit 0
    fi
fi

mkdir -p "$PILOT_DIR"

if [ "$FROM_EXAMPLES" = true ] && [ -f "$DATA_PATH/examples/processes.yaml" ]; then
    echo "Copying process structure from examples..."
    cp "$DATA_PATH/examples/processes.yaml" "$PILOT_DIR/processes.yaml"
    # Create empty assessments file — pilot starts fresh
    cat > "$PILOT_DIR/assessments.yaml" <<'YAML'
# Pilot assessments — created by init-pilot.sh
# Assessments will be added through the UI.
assessments: []
YAML
    echo "  Copied processes.yaml (structure only)"
    echo "  Created empty assessments.yaml"
else
    # Create minimal empty structure
    cat > "$PILOT_DIR/processes.yaml" <<'YAML'
# Pilot process structure — add your areas, streams, subprocesses, and interfaces.
areas: []
streams: []
subprocesses: []
interfaces: []
YAML
    cat > "$PILOT_DIR/assessments.yaml" <<'YAML'
# Pilot assessments — add assessments through the UI or manually here.
assessments: []
YAML
    echo "  Created empty processes.yaml"
    echo "  Created empty assessments.yaml"
fi

echo "───────────────────────────────────────────────────"
echo "  Dataset '$DATASET_NAME' is ready."
echo "  Select it in the UI dataset dropdown or use"
echo "  ?dataset=$DATASET_NAME in API calls."
echo "═══════════════════════════════════════════════════"
