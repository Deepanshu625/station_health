"""Shared fixtures for integration tests (API + real PostgreSQL)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from freezegun import freeze_time
from rest_framework.test import APIClient

FROZEN_NOW = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def frozen_clock():
    """Time-dependent tests must not depend on real wall-clock timing."""
    with freeze_time(FROZEN_NOW):
        yield


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def now() -> datetime:
    return FROZEN_NOW


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def report_payload(
    station_id: str = "CP-TEST-0001",
    timestamp: datetime | None = None,
    connectivity_status: str = "online",
    latency_ms: int = 150,
    error_count: int = 0,
    firmware_version: str = "2.4.0",
    region: str | None = None,
    base_time: datetime | None = None,
    minutes_ago: float = 0,
) -> dict:
    if timestamp is None:
        base = base_time or datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
        timestamp = base - timedelta(minutes=minutes_ago)
    payload = {
        "station_id": station_id,
        "timestamp": iso(timestamp),
        "connectivity_status": connectivity_status,
        "latency_ms": latency_ms,
        "error_count": error_count,
        "firmware_version": firmware_version,
    }
    if region is not None:
        payload["region"] = region
    return payload
