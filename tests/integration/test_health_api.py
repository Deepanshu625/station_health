"""Integration tests for GET /api/v1/stations/{id}/health."""

from __future__ import annotations

import pytest

from .conftest import report_payload

pytestmark = pytest.mark.django_db

REPORTS_URL = "/api/v1/reports"


def health_url(station_id: str) -> str:
    return f"/api/v1/stations/{station_id}/health"


def test_health_response_shape(api_client, now):
    api_client.post(REPORTS_URL, report_payload(base_time=now, region="North"), format="json")

    response = api_client.get(health_url("CP-TEST-0001"))

    assert response.status_code == 200
    body = response.data
    assert body["station_id"] == "CP-TEST-0001"
    assert body["region"] == "North"
    assert body["hygiene_score"] == 100.0
    assert body["is_poor"] is False
    assert body["score_components"]["availability"]["points"] == 40.0


def test_health_returns_404_for_unknown_station(api_client):
    response = api_client.get(health_url("UNKNOWN-STATION"))

    assert response.status_code == 404
    assert response.data["error"]["code"] == "station_not_found"
