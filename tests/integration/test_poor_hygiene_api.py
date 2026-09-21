"""Integration tests for GET /api/v1/stations/poor-hygiene."""

from __future__ import annotations

import pytest

from .conftest import report_payload

pytestmark = pytest.mark.django_db

REPORTS_URL = "/api/v1/reports"
URL = "/api/v1/stations/poor-hygiene"


def _seed_poor_station(api_client, now, station_id, region="North"):
    api_client.post(
        REPORTS_URL,
        report_payload(
            base_time=now,
            station_id=station_id,
            region=region,
            connectivity_status="offline",
            error_count=50,
            latency_ms=0,
        ),
        format="json",
    )


def _seed_healthy_station(api_client, now, station_id, region="North"):
    api_client.post(
        REPORTS_URL,
        report_payload(base_time=now, station_id=station_id, region=region),
        format="json",
    )


def test_lists_only_poor_stations_ordered_by_score(api_client, now):
    _seed_poor_station(api_client, now, "CP-A")
    _seed_healthy_station(api_client, now, "CP-B")

    response = api_client.get(URL)

    assert response.status_code == 200
    ids = [r["station_id"] for r in response.data["results"]]
    assert ids == ["CP-A"]


def test_region_filter(api_client, now):
    _seed_poor_station(api_client, now, "CP-N", region="North")
    _seed_poor_station(api_client, now, "CP-S", region="South")

    response = api_client.get(URL, {"region": "North"})

    ids = [r["station_id"] for r in response.data["results"]]
    assert ids == ["CP-N"]


def test_limit_bounds_the_results_and_count_reflects_total(api_client, now):
    for i in range(3):
        _seed_poor_station(api_client, now, f"CP-{i:03d}")

    response = api_client.get(URL, {"limit": "2"})

    assert len(response.data["results"]) == 2
    assert response.data["count"] == 3


def test_invalid_limit_returns_400(api_client):
    response = api_client.get(URL, {"limit": "0"})

    assert response.status_code == 400
    assert response.data["error"]["code"] == "invalid_query_param"
