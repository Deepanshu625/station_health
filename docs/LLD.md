# Station Health Service — Low-Level Design

This document specifies the parameters, schema and API contract for the service described in [DESIGN.md](../DESIGN.md). It reflects what is actually implemented; forward-looking extensions (queueing, alerting, anomaly detection, multi-region, auth) are documented in DESIGN.md §6–8 and §13, not here.

**Conventions**

- Timestamps are ISO 8601 with a timezone offset on input, returned in UTC with a `Z` suffix.
- Scores are floats in 0–100, rounded to 2 decimals.
- JSON field names are `snake_case`. The base path for the API is `/api/v1`.

---

## 1. Configuration

Read once in `config/settings.py` from environment variables, exposed to services as immutable `ScoringConfig` / `AppConfig` dataclasses (`stations/config.py`). Defaults are chosen so `docker compose up` works with no `.env` file.

### 1.1 Scoring

| Env var | Default | Meaning |
|---|---|---|
| `WEIGHT_AVAILABILITY` | `40` | Points for availability. |
| `WEIGHT_LATENCY` | `25` | Points for latency. |
| `WEIGHT_ERRORS` | `25` | Points for errors. |
| `WEIGHT_FIRMWARE` | `10` | Points for firmware. |
| `LATENCY_FULL_MS` | `200` | Latency at or below this earns full latency points. |
| `LATENCY_ZERO_MS` | `2000` | Latency at or above this earns zero. |
| `ERRORS_ZERO_AT` | `10` | Error count at or above this earns zero. |
| `MIN_SUPPORTED_FIRMWARE` | `2.2.0` | Firmware below this earns zero firmware points. |
| `POOR_THRESHOLD` | `60` | `score < POOR_THRESHOLD` → station is poor. |

Validation at startup: weights must sum to 100, `LATENCY_FULL_MS < LATENCY_ZERO_MS`, `MIN_SUPPORTED_FIRMWARE` must parse as a version. The app refuses to start otherwise.

### 1.2 API and ingestion

| Env var | Default | Meaning |
|---|---|---|
| `MAX_BATCH_SIZE` | `500` | Max reports per ingest request. |
| `MAX_CLOCK_SKEW_SECONDS` | `86400` | Reports timestamped further in the future are rejected. |
| `MAX_REPORT_AGE_DAYS` | `30` | Older reports are rejected. |
| `DATA_UPLOAD_MAX_MEMORY_SIZE` | `1048576` | Django request body cap (bytes). |
| `DEFAULT_PAGE_SIZE` | `50` | Default `limit` on the poor-hygiene list. |
| `MAX_PAGE_SIZE` | `200` | Upper bound for `limit`. |

### 1.3 Runtime

| Env var | Default |
|---|---|
| `DATABASE_URL` | `postgres://health:health@db:5432/health` |
| `DJANGO_DEBUG` | `false` |
| `DJANGO_SECRET_KEY` | random per container start in dev; required in prod |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` |
| `WEB_CONCURRENCY` | `3` |
| `LOG_LEVEL` | `INFO` (JSON logs to stdout) |
| `DASHBOARD_REFRESH_SECONDS` | `30` |

---

## 2. Data Model

### 2.1 `stations` (latest state)

```python
class Station(models.Model):
    station_id           = models.CharField(primary_key=True, max_length=64)
    region               = models.CharField(max_length=32, default="unassigned", db_index=True)
    last_reported_at     = models.DateTimeField(null=True, db_index=True)
    connectivity_status  = models.CharField(max_length=8, choices=Connectivity.choices, null=True)
    latency_ms           = models.PositiveIntegerField(null=True)
    error_count          = models.PositiveIntegerField(null=True)
    firmware_version     = models.CharField(max_length=32, null=True)
    hygiene_score        = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    score_components     = models.JSONField(null=True)   # shape in §3.3
    is_poor              = models.BooleanField(default=False, db_index=True)
    created_at            = models.DateTimeField(auto_now_add=True)
    updated_at            = models.DateTimeField(auto_now=True)
```

A station row is created on its first report. `region` is set from the first report that carries one and never changes after that.

### 2.2 `health_reports` (append-only history)

```python
class HealthReport(models.Model):
    id                   = models.BigAutoField(primary_key=True)
    station              = models.ForeignKey(Station, on_delete=models.CASCADE,
                                             db_column="station_id", related_name="reports")
    reported_at          = models.DateTimeField()   # device timestamp (payload "timestamp")
    received_at          = models.DateTimeField()   # server time at ingest
    connectivity_status  = models.CharField(max_length=8, choices=Connectivity.choices)
    latency_ms           = models.PositiveIntegerField()
    error_count          = models.PositiveIntegerField()
    firmware_version     = models.CharField(max_length=32)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["station", "reported_at"], name="uniq_station_reported_at"),
        ]
```

The unique constraint makes a retried report a no-op (`IntegrityError` on insert, caught and counted as a duplicate).

### 2.3 Enums

```python
class Connectivity(models.TextChoices):
    ONLINE = "online"
    OFFLINE = "offline"
```

---

## 3. Scoring (`stations/services/scoring.py`)

Pure function, no Django imports, no DB access, no `now()`. Computed from a single `ReportSnapshot` (`connectivity_status`, `latency_ms`, `error_count`, `firmware_version`).

### 3.1 Formula

Let `clamp(x) = min(1, max(0, x))`.

| Component | Factor (0–1) |
|---|---|
| Availability | `1` if `online`, else `0` |
| Latency | `0` if offline; else `clamp((LATENCY_ZERO_MS − latency_ms) / (LATENCY_ZERO_MS − LATENCY_FULL_MS))` |
| Errors | `clamp(1 − error_count / ERRORS_ZERO_AT)` |
| Firmware | `1` if version ≥ `MIN_SUPPORTED_FIRMWARE`, `0` if lower, `0.5` if unparseable (`packaging.version.InvalidVersion`) |

```
score   = round(W_a·availability + W_l·latency + W_e·errors + W_f·firmware, 2)
is_poor = score < POOR_THRESHOLD
```

### 3.2 Out-of-order handling

Every report is stored in `health_reports` regardless of order. The `stations` row (latest fields, current score) is only overwritten if the incoming `reported_at` is `>=` the station's stored `last_reported_at`. A late report is preserved in history but never regresses the current state. See DESIGN.md §13 for the concurrency trade-off this implies.

### 3.3 `score_components` JSON shape

```json
{
  "availability": {"points": 40.0, "max": 40, "connectivity_status": "online"},
  "latency":      {"points": 5.0,  "max": 25, "latency_ms": 1640},
  "errors":       {"points": 12.5, "max": 25, "error_count": 5},
  "firmware":     {"points": 10.0, "max": 10, "version": "2.4.0", "minimum": "2.2.0", "status": "supported"}
}
```

`latency.latency_ms` is `null` when the station is offline. `firmware.status` is one of `supported`, `outdated`, `unknown`.

---

## 4. Ingestion (`stations/services/ingestion.py`)

For each report in the request (one call per report, so one bad/duplicate report in a batch never blocks the rest from being attempted... except validation, which is all-or-nothing per §5.2):

1. `get_or_create` the `Station` row; if it's new, set `region` from the report if present, else `unassigned`. If the station already exists with `region="unassigned"` and this report carries one, set it once.
2. Insert into `health_reports` inside a savepoint; an `IntegrityError` (duplicate `station_id` + `reported_at`) is caught and counted as a duplicate — nothing else about the request fails.
3. If `reported_at >= station.last_reported_at` (or the station has never reported), recompute the score from this report via `scoring.compute_score` and overwrite the station's latest fields, `hygiene_score`, `score_components`, `is_poor`.
4. Save the station.

No row locking, no multi-row raw SQL, no per-report score history — see DESIGN.md §13.

---

## 5. API Reference

### 5.1 Common rules

- **Content type:** JSON only. Anything else on `POST` → `415`.
- **Auth:** none on any endpoint.
- **Error shape**, from the custom exception handler, on every non-2xx response:

```json
{
  "error": {
    "code": "validation_error",
    "message": "1 of 3 reports is invalid; nothing was stored.",
    "details": { "1": { "latency_ms": ["Ensure this value is greater than or equal to 0."] } }
  }
}
```

| `code` | HTTP | When |
|---|---|---|
| `validation_error` | 400 | Body or field fails validation |
| `invalid_query_param` | 400 | Bad `limit`, `group_by`, etc. |
| `batch_too_large` | 400 | More than `MAX_BATCH_SIZE` reports |
| `malformed_json` | 400 | Body isn't parseable JSON |
| `station_not_found` | 404 | Unknown `station_id` |
| `unsupported_media_type` | 415 | Non-JSON body |
| `internal_error` | 500 | Unhandled exception |
| `service_unavailable` | 503 | Health check can't reach the database |

### 5.2 `POST /api/v1/reports`

One report (JSON object) or a batch (array of 1–500 objects), validated all-or-nothing.

| Field | Type | Required | Validation |
|---|---|---|---|
| `station_id` | string | yes | 1–64 chars, `^[A-Za-z0-9_-]+$` |
| `timestamp` | string (ISO 8601) | yes | Must include a timezone; not more than `MAX_CLOCK_SKEW_SECONDS` in the future; not older than `MAX_REPORT_AGE_DAYS` |
| `connectivity_status` | string | yes | `online` or `offline` |
| `latency_ms` | integer | yes | 0–600000 |
| `error_count` | integer | yes | 0–100000 |
| `firmware_version` | string | yes | 1–32 chars |
| `region` | string | no | 1–32 chars, `^[A-Za-z0-9 _-]+$` |

Unknown fields are rejected. Response `201`: `{"accepted": N, "duplicates": M}`. Duplicates are not errors, so client retries are safe.

### 5.3 `GET /api/v1/stations/{station_id}/health`

```json
{
  "station_id": "CP-NTH-1022",
  "region": "North",
  "connectivity_status": "online",
  "latency_ms": 180,
  "error_count": 0,
  "firmware_version": "2.4.0",
  "last_reported_at": "2026-09-20T09:02:04Z",
  "hygiene_score": 100.0,
  "is_poor": false,
  "score_components": { "...": "shape in §3.3" }
}
```

`404` (`station_not_found`) if unknown.

### 5.4 `GET /api/v1/stations/poor-hygiene`

Stations with `is_poor = true`, lowest score first.

| Param | Type | Default | Validation |
|---|---|---|---|
| `region` | string | all | exact match |
| `limit` | integer | `DEFAULT_PAGE_SIZE` | 1–`MAX_PAGE_SIZE` |

```json
{
  "results": [
    {"station_id": "CP-WST-0419", "region": "West", "hygiene_score": 31.0,
     "connectivity_status": "offline", "last_reported_at": "2026-09-20T09:03:01Z"}
  ],
  "count": 47
}
```

`count` is the total number of poor stations matching `region`, independent of `limit`.

### 5.5 `GET /api/v1/metrics`

| Param | Type | Default |
|---|---|---|
| `group_by` | enum (`region`) | none |

```json
{
  "generated_at": "2026-09-20T09:04:10Z",
  "overall": {"stations": 1200, "online": 1146, "offline": 54, "poor": 38,
              "avg_latency_ms": 184.5, "avg_hygiene_score": 85.9},
  "groups": [
    {"region": "North", "stations": 300, "online": 289, "offline": 11,
     "poor": 8, "avg_latency_ms": 172.0, "avg_hygiene_score": 87.1}
  ]
}
```

`groups` is empty without `group_by`. `avg_latency_ms` averages the latest `latency_ms` of stations whose latest status is `online`; `null` if none are online. Computed with a single `GROUP BY` query.

### 5.6 Operational endpoints

| Endpoint | Response |
|---|---|
| `GET /healthz` | `200 {"status": "ok", "database": "ok"}` after a `SELECT 1`; `503` otherwise |
| `GET /api/schema/` | OpenAPI 3 document (drf-spectacular) |
| `GET /api/docs/` | Swagger UI |
| `GET /dashboard/` | Dashboard HTML |

---

## 6. Dashboard (`dashboard/` app)

Plain Django template + ES modules (`app.js`, `api.js`, `render.js`, `format.js`) + `styles.css`, served at `/dashboard/`. No build step, no third-party JS dependency. Uses only the public API above.

- **Overview (`#/`):** KPI tiles (stations, online/%, offline, poor, avg latency, avg score) from `/metrics`; a poor-hygiene table with a region filter pill row and a "Show more" button (`limit`, no cursor) from `/stations/poor-hygiene`; a by-region card list from `/metrics?group_by=region`.
- **Station drill-down (`#/stations/{id}`):** station header (region, firmware, connectivity, last report), a "Poor hygiene" banner when `is_poor`, and a score card with the four `score_components` rows.
- Polls every `DASHBOARD_REFRESH_SECONDS`; skips a tick if a request is in flight; pauses while the tab is hidden and refreshes on return; shows a warning banner on a failed refresh without discarding the last good data.
- Renders all API data (station IDs, firmware versions, etc. — untrusted device input) via `textContent` / `createElement`, never `innerHTML`.

---

## 7. Project Layout

```
station_health/
  config/                   # settings.py, urls.py, wsgi.py, logging.py
  stations/
    models.py
    serializers.py
    views.py
    urls.py
    exceptions.py           # custom exception handler (§5.1)
    config.py               # ScoringConfig / AppConfig dataclasses + validation
    middleware.py           # request-ID + structured logging
    services/
      types.py  scoring.py  ingestion.py  queries.py  metrics.py
    migrations/
  dashboard/                # §6
  tests/
    unit/                   # scoring, config validation
    integration/            # API + real PostgreSQL
  docs/
    architecture.svg
    LLD.md
  DESIGN.md
  README.md
  Dockerfile
  docker-compose.yml
  pyproject.toml            # ruff, pytest, coverage config
  .github/workflows/ci.yml
```
