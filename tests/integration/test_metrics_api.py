"""Integration tests for GET /api/v1/metrics."""

from __future__ import annotations

import pytest

from .conftest import report_payload

pytestmark = pytest.mark.django_db

REPORTS_URL = "/api/v1/reports"
URL = "/api/v1/metrics"


def test_overall_metrics(api_client, now):
    api_client.post(
        REPORTS_URL,
        report_payload(
            base_time=now, station_id="CP-1", connectivity_status="online", latency_ms=100
        ),
        format="json",
    )
    api_client.post(
        REPORTS_URL,
        report_payload(base_time=now, station_id="CP-2", connectivity_status="offline"),
        format="json",
    )

    response = api_client.get(URL)

    assert response.status_code == 200
    overall = response.data["overall"]
    assert overall["stations"] == 2
    assert overall["online"] == 1
    assert overall["offline"] == 1
    assert overall["avg_latency_ms"] == 100.0
    assert response.data["groups"] == []


def test_group_by_region(api_client, now):
    api_client.post(
        REPORTS_URL, report_payload(base_time=now, station_id="CP-N", region="North"), format="json"
    )
    api_client.post(
        REPORTS_URL, report_payload(base_time=now, station_id="CP-S", region="South"), format="json"
    )

    response = api_client.get(URL, {"group_by": "region"})

    regions = {g["region"]: g for g in response.data["groups"]}
    assert set(regions.keys()) == {"North", "South"}
    assert regions["North"]["stations"] == 1


def test_avg_latency_is_null_when_no_station_online(api_client, now):
    api_client.post(
        REPORTS_URL, report_payload(base_time=now, connectivity_status="offline"), format="json"
    )

    response = api_client.get(URL)

    assert response.data["overall"]["avg_latency_ms"] is None


def test_invalid_group_by_returns_400(api_client):
    response = api_client.get(URL, {"group_by": "bogus"})

    assert response.status_code == 400
    assert response.data["error"]["code"] == "invalid_query_param"
