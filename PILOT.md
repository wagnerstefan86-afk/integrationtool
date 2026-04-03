# Harmonizer — Pilot Operation Guide

This guide covers controlled server-based pilot deployment of the Harmonizer tool.

## Prerequisites

- Docker >= 20.10
- Docker Compose >= 2.0
- Bash (Linux/macOS/WSL)

## Quick Start

```bash
# 1. Configure
cp .env.example .env        # adjust ports/paths if needed

# 2. Start (creates directories, seeds data, builds, launches)
./scripts/start.sh --build

# 3. Open
#    Frontend:  http://localhost:3001
#    API:       http://localhost:8001/health
```

## Directory Structure

All persistent data lives on the host under `deploy/` (configurable via `.env`):

```
deploy/
├── data/
│   ├── examples/     # Shipped demo data (read-only reference)
│   └── pilot/        # Your pilot assessment data
├── reports/
│   ├── generated/    # Auto-generated analysis reports
│   └── reviewed/     # Manually approved reports
├── logs/             # Application logs (harmonizer.log)
└── backups/          # Timestamped backup archives
```

**Data and code are strictly separated.** Containers mount `deploy/` volumes;
source code stays inside the image.

## Dataset Separation

| Dataset | Purpose | How to create |
|---------|---------|---------------|
| `examples` | Shipped demo data, 4 areas / 15 streams | Copied automatically on first start |
| `pilot` | Your real assessment data | `./scripts/init-pilot.sh` |
| Custom | Additional assessment cycles | `./scripts/init-pilot.sh my_cycle_name` |

Select the active dataset in the UI dropdown (bottom-left sidebar) or pass
`?dataset=pilot` to API calls.

### Initialize a Pilot Dataset

```bash
# Empty pilot dataset
./scripts/init-pilot.sh

# Pilot with process structure copied from examples
./scripts/init-pilot.sh --from-examples

# Custom named dataset
./scripts/init-pilot.sh q2_2026_assessment
```

## Configuration

All settings live in `.env` (copied from `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | production | Environment label (shown in UI/health) |
| `BACKEND_PORT` | 8001 | API port on host |
| `FRONTEND_PORT` | 3001 | Frontend port on host |
| `DATA_PATH` | ./deploy/data | Host path for YAML data volumes |
| `REPORT_PATH` | ./deploy/reports | Host path for report volumes |
| `LOG_PATH` | ./deploy/logs | Host path for log volumes |

Version metadata (`APP_VERSION`, `GIT_COMMIT`, `BUILD_DATE`) is set
automatically by `scripts/start.sh` — do not edit manually.

## Operations

### Start / Stop / Rebuild

```bash
./scripts/start.sh              # start (build only if needed)
./scripts/start.sh --build      # force rebuild images
./scripts/start.sh --stop       # stop all services
```

### Logs

```bash
docker compose logs -f              # all services
docker compose logs -f backend      # backend only
tail -f deploy/logs/harmonizer.log  # persistent log file
```

### Health Check

```bash
curl -s http://localhost:8001/health | python3 -m json.tool
```

Returns version, git commit, build date, environment, and path info.
Both containers have Docker health checks — visible via `docker ps`.

### Backup

```bash
./scripts/backup.sh                    # default: deploy/backups/
./scripts/backup.sh /mnt/nas/backups   # custom backup target
```

Creates a timestamped `.tar.gz` archive of all YAML data and reports.
Automatically prunes old backups, keeping the last 10.

**Recommended:** Schedule daily backups via cron:
```cron
0 2 * * * /path/to/harmonizer/scripts/backup.sh >> /var/log/harmonizer-backup.log 2>&1
```

### Restore from Backup

```bash
# Stop services
./scripts/start.sh --stop

# Extract backup over existing data
tar -xzf deploy/backups/harmonizer-backup-2026-04-03_02-00-00.tar.gz \
    -C deploy/ --strip-components=0

# Restart
./scripts/start.sh
```

## Pilot Workflow

1. **Setup:** Run `./scripts/start.sh --build` and `./scripts/init-pilot.sh --from-examples`
2. **Assess:** Switch to `pilot` dataset in the UI, fill in assessments per stream
3. **Review:** Use the Decisions page to review computed recommendations, apply overrides where needed
4. **Report:** Generate a report via the Reports page or API (`POST /api/analyze`)
5. **Backup:** Run `./scripts/backup.sh` after each assessment session
6. **Iterate:** Repeat steps 2-5 as assessment data is refined

## Version Traceability

Every report and the UI footer show:
- **App version** (e.g. 0.9.0)
- **Git commit** (short hash)
- **Build date** (ISO 8601)

This ensures every report can be traced back to the exact code version.

## API Quick Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check with version info |
| `GET` | `/api/dashboard?dataset=pilot` | Dashboard statistics |
| `POST` | `/api/analyze` | Run full analysis pipeline |
| `POST` | `/api/decisions/compute/{stream_id}` | Compute decision for a stream |
| `GET` | `/api/reviews` | List all reviews |
| `PUT` | `/api/reviews` | Save a review |
| `GET` | `/api/reports` | List generated reports |
| `GET` | `/api/reports/{name}` | Retrieve a report |

All CRUD endpoints accept `?dataset=pilot` to operate on the pilot dataset.

## CLI Access

The CLI is available inside the backend container:

```bash
docker compose exec backend harmonizer analyze \
    --data-dir /data/pilot -o /reports/generated/pilot_report.md
```

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Frontend shows "Backend unreachable" | `docker compose logs backend` — is the backend healthy? |
| Health check fails | `curl localhost:8001/health` — check ports, firewall |
| Empty dataset dropdown | Ensure `deploy/data/` has at least one subdirectory with YAML files |
| "No assessment found" on decision compute | Create and complete an assessment for the stream first |
| Backup script fails | Check disk space and write permissions on backup directory |
