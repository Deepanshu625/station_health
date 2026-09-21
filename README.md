# Station Health Service

## 1. Overview

Station Health ingests periodic health reports from EV charging stations (connectivity, latency, error counts, firmware version), computes a **network hygiene score** per station from its most recent report, and exposes a REST API plus a small NOC dashboard so operators can find problem stations. A station is flagged **poor** when its score falls below 60.

![High-level architecture](docs/architecture.svg)

Full design rationale is in [DESIGN.md](DESIGN.md); the parameter-level specification is in [docs/LLD.md](docs/LLD.md).

## 2. Quick start

**Prerequisites:** Docker and Docker Compose. Nothing else needs to be installed locally.

```bash
cp .env.example .env
docker compose up --build
```

Once `app` is healthy, open:

- Dashboard: <http://localhost:8000/dashboard/>
- Swagger UI: <http://localhost:8000/api/docs/>
- Health check: <http://localhost:8000/healthz>

The dashboard starts empty until you post some reports — see the next section for a curl example, or `POST` a few for different stations to see the overview populate.

### Running locally without Docker

If you don't have Docker, or prefer to run against your own PostgreSQL, here's the full path from a bare checkout to a running dashboard.

**1. Create and activate a virtual environment**

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

**2. Install dependencies**

```bash
pip install -r requirements-dev.txt   # runtime deps + pytest/ruff
```

**3. Get a local PostgreSQL 16 running**

macOS (Homebrew):

```bash
brew install postgresql@16
brew services start postgresql@16
createuser -s health
createdb -O health health
psql -d health -c "ALTER USER health WITH PASSWORD 'health';"
```

Any Postgres 16 instance works (a Linux package, an existing server, etc.) — just adjust the connection details in the next step to match it.

**4. Configure environment variables**

```bash
cp .env.example .env
```

Edit `.env` so it points at your local database and runs in debug mode:

```
DATABASE_URL=postgres://health:health@127.0.0.1:5432/health
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=local-dev-secret
```

**5. Apply migrations**

```bash
set -a && source .env && set +a
python manage.py migrate
```

**6. Run the dev server**

```bash
python manage.py runserver 8000
```

**7. Create a few stations** (in another terminal — the `.venv`/`.env` don't need to be active for `curl`)

```bash
curl -s -X POST http://localhost:8000/api/v1/reports \
  -H "Content-Type: application/json" \
  -d '{"station_id":"CP-NTH-1022","timestamp":"2026-09-21T05:47:39Z","connectivity_status":"online","latency_ms":180,"error_count":0,"firmware_version":"2.4.0","region":"North"}'

curl -s -X POST http://localhost:8000/api/v1/reports \
  -H "Content-Type: application/json" \
  -d '[{"station_id":"CP-EST-0201","timestamp":"2026-09-21T05:47:39Z","connectivity_status":"online","latency_ms":120,"error_count":0,"firmware_version":"2.4.0","region":"East"},
       {"station_id":"CP-WST-0419","timestamp":"2026-09-21T05:47:39Z","connectivity_status":"offline","latency_ms":0,"error_count":30,"firmware_version":"1.7.0","region":"West"}]'
```

`timestamp` must be ISO 8601 with a timezone (the `Z` suffix = UTC), not more than 1 day in the future, and not older than 30 days. The example above is a fixed, already-valid timestamp — if it's been more than a few weeks since you're reading this, replace it with any recent UTC time in the same `YYYY-MM-DDTHH:MM:SSZ` format (e.g. from `date -u +"%Y-%m-%dT%H:%M:%SZ"`).

**8. Open it**

- Dashboard: <http://localhost:8000/dashboard/>
- Swagger UI: <http://localhost:8000/api/docs/>
- Health check: <http://localhost:8000/healthz>

**9. Run the tests**

```bash
pytest --cov --cov-report=term-missing
```

## 3. Running tests

In Docker, against the real Postgres service defined in `docker-compose.yml`:

```bash
docker compose run --rm app pytest
```

With coverage:

```bash
docker compose run --rm app pytest --cov --cov-report=term-missing
```

Locally, with your own Postgres instance (set `DATABASE_URL` to point at it first, as in §2 above):

```bash
pytest --cov --cov-report=term-missing
```

## 4. Try the API

All examples assume the default base URL `http://localhost:8000`. No authentication is required on any endpoint (see DESIGN.md §8 for why).

**Ingest a single report:**

```bash
curl -s -X POST http://localhost:8000/api/v1/reports \
  -H "Content-Type: application/json" \
  -d '{
        "station_id": "CP-NTH-1022",
        "timestamp": "2026-09-20T14:32:04Z",
        "connectivity_status": "online",
        "latency_ms": 180,
        "error_count": 0,
        "firmware_version": "2.4.0",
        "region": "North"
      }'
```

**Ingest a batch:**

```bash
curl -s -X POST http://localhost:8000/api/v1/reports \
  -H "Content-Type: application/json" \
  -d '[
        {"station_id": "CP-WST-0419", "timestamp": "2026-09-20T14:32:04Z",
         "connectivity_status": "offline", "latency_ms": 0, "error_count": 30,
         "firmware_version": "1.7.0", "region": "West"},
        {"station_id": "CP-EST-0201", "timestamp": "2026-09-20T14:32:04Z",
         "connectivity_status": "online", "latency_ms": 120, "error_count": 0,
         "firmware_version": "2.4.0", "region": "East"}
      ]'
```

**Retry the same report (duplicates are safe, not errors):**

```bash
curl -s -X POST http://localhost:8000/api/v1/reports \
  -H "Content-Type: application/json" \
  -d '{"station_id": "CP-NTH-1022", "timestamp": "2026-09-20T14:32:04Z",
       "connectivity_status": "online", "latency_ms": 180, "error_count": 0,
       "firmware_version": "2.4.0"}'
# => {"accepted": 0, "duplicates": 1}
```

**A validation error (negative latency):**

```bash
curl -s -X POST http://localhost:8000/api/v1/reports \
  -H "Content-Type: application/json" \
  -d '{"station_id": "CP-NTH-1022", "timestamp": "2026-09-20T14:32:04Z",
       "connectivity_status": "online", "latency_ms": -5, "error_count": 0,
       "firmware_version": "2.4.0"}'
# => 400 {"error": {"code": "validation_error", "message": "...", "details": {...}}}
```

**Station health:**

```bash
curl -s http://localhost:8000/api/v1/stations/CP-NTH-1022/health
```

**Poor-hygiene stations:**

```bash
curl -s "http://localhost:8000/api/v1/stations/poor-hygiene?region=West&limit=20"
```

**Fleet metrics, grouped by region:**

```bash
curl -s "http://localhost:8000/api/v1/metrics?group_by=region"
```

**Liveness check:**

```bash
curl -s http://localhost:8000/healthz
```

## 5. Configuration

The full list of environment variables and defaults is in [docs/LLD.md §1](docs/LLD.md#1-configuration); `.env.example` lists all of them. The most important:

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgres://health:health@db:5432/health` | Postgres connection string |
| `POOR_THRESHOLD` | `60` | Score below this is "poor" |
| `DASHBOARD_REFRESH_SECONDS` | `30` | Dashboard polling interval |
| `DJANGO_DEBUG` | `false` | Must be `false` outside local dev |

## 6. Project structure

```
station_health/
  config/                    # Django settings, root URLs, WSGI, JSON log formatter
  stations/
    models.py                # Station, HealthReport
    serializers.py           # POST /reports request validation only
    views.py                 # thin DRF views (HTTP only)
    urls.py                  # /api/v1 routes
    exceptions.py            # single error-shape DRF exception handler
    middleware.py            # request-ID + structured request logging
    config.py                # ScoringConfig / AppConfig dataclasses + validation
    services/
      types.py                # pure dataclasses shared across services
      scoring.py              # pure scoring function (no Django/DB/now())
      ingestion.py            # per-report upsert of latest state + score
      queries.py              # read-side queries (health, poor-hygiene)
      metrics.py              # fleet aggregates
    migrations/
  dashboard/                 # Django template + ES-module JS + CSS
  tests/
    unit/                    # scoring, config validation — no database
    integration/             # API + real PostgreSQL
  docs/
    architecture.svg
    LLD.md
  DESIGN.md
  README.md
  Dockerfile
  docker-compose.yml
  pyproject.toml             # ruff, pytest, coverage config
  .github/workflows/ci.yml
```

## 7. Design documents

- [DESIGN.md](DESIGN.md) — architecture and reasoning
- [docs/LLD.md](docs/LLD.md) — parameter-level specification

## 8. Assumptions

Carried over from [DESIGN.md §1](DESIGN.md#1-assumptions):

| Area | Assumption |
|---|---|
| Report frequency | Each station reports roughly once per minute; retries and duplicates are expected. |
| Ordering | Reports can arrive late or out of order (flaky cellular links, backlog flush after reconnect). |
| Region | Not in the specified payload. The API accepts an optional `region` field; a station keeps the region from its first report, defaulting to `unassigned`. |
| Firmware | "Outdated" means below a configured minimum supported version. Unparseable versions count as unknown. |
| Auth | Not implemented; every endpoint is open. |
| Scoring basis | Computed from a station's single most recent report, not a rolling window — see DESIGN.md §4 for the trade-off. |

Additional assumptions made while implementing:

- No authentication, cursor pagination, per-report score history, or staleness/event-log features are implemented; DESIGN.md §13 lists these and why, with pointers to how each would be added.
- An empty batch (`[]`) on `POST /reports` is rejected as a validation error, since the spec implies at least one report per request.

## 9. AI usage

_To be completed by the author._

## 10. Troubleshooting

- **Port already in use:** another process is bound to `8000` or `5432`. Stop it, or change the host port mapping in `docker-compose.yml`.
- **App can't reach the database yet:** the `app` service waits for `db`'s healthcheck, but if you see connection errors right after `up`, wait a few seconds and retry — Postgres can take a moment to finish initializing on the very first run.
- **Resetting all data:** `docker compose down -v` removes the named `pgdata` volume along with the containers, giving you a clean database on the next `up`.
