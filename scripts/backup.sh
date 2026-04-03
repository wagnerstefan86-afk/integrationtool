#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Harmonizer — Backup Script
# Creates a timestamped archive of YAML data and reports.
#
# Usage:
#   ./scripts/backup.sh                    # uses defaults from .env
#   ./scripts/backup.sh /path/to/backups   # custom backup directory
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
REPORT_PATH="${REPORT_PATH:-$PROJECT_DIR/deploy/reports}"
BACKUP_DIR="${1:-$PROJECT_DIR/deploy/backups}"
TIMESTAMP="$(date +%Y-%m-%d_%H-%M-%S)"
BACKUP_NAME="harmonizer-backup-${TIMESTAMP}"
BACKUP_FILE="${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"

echo "═══════════════════════════════════════════════════"
echo "  Harmonizer Backup"
echo "═══════════════════════════════════════════════════"
echo "  Data path:   $DATA_PATH"
echo "  Report path: $REPORT_PATH"
echo "  Backup dir:  $BACKUP_DIR"
echo "  Timestamp:   $TIMESTAMP"
echo "───────────────────────────────────────────────────"

# Validate source directories exist
if [ ! -d "$DATA_PATH" ]; then
    echo "ERROR: Data directory not found: $DATA_PATH"
    exit 1
fi

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Build a temp staging directory so the archive has clean paths
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

echo "Copying data..."
cp -r "$DATA_PATH" "$STAGING/data"

if [ -d "$REPORT_PATH" ]; then
    echo "Copying reports..."
    cp -r "$REPORT_PATH" "$STAGING/reports"
fi

# Add metadata
cat > "$STAGING/backup-info.txt" <<INFO
Harmonizer Backup
═════════════════
Timestamp:  $TIMESTAMP
Hostname:   $(hostname)
Data path:  $DATA_PATH
Report path: $REPORT_PATH
INFO

# Create archive
echo "Creating archive..."
tar -czf "$BACKUP_FILE" -C "$STAGING" .

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "───────────────────────────────────────────────────"
echo "  Backup complete: $BACKUP_FILE ($SIZE)"
echo "═══════════════════════════════════════════════════"

# Prune old backups — keep last 10
BACKUP_COUNT=$(find "$BACKUP_DIR" -name 'harmonizer-backup-*.tar.gz' | wc -l)
if [ "$BACKUP_COUNT" -gt 10 ]; then
    echo "Pruning old backups (keeping last 10)..."
    find "$BACKUP_DIR" -name 'harmonizer-backup-*.tar.gz' -printf '%T@ %p\n' \
        | sort -n | head -n -10 | awk '{print $2}' | xargs rm -f
fi
