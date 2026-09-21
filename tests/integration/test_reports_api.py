"""Integration tests for POST /api/v1/reports against real PostgreSQL."""

from __future__ import annotations

from datetime import timedelta

import pytest

from stations.models import HealthReport, Station

from .conftest import report_payload

pytestmark = pytest.mark.django_db

URL = "/api/v1/reports"


def test_single_report_ingest_returns_201_with_counts(api_client, now):
    response = api_client.post(URL, report_payload(base_time=now), format="json")

    assert response.status_code == 201
    assert response.data == {"accepted": 1, "duplicates": 0}


def test_batch_ingest_stores_latest_state_and_score(api_client, now):
    payload = [
        report_payload(base_time=now, minutes_ago=1, latency_ms=150, error_count=0),
        report_payload(base_time=now, minutes_ago=0, latency_ms=180, error_count=1),
    ]

    response = api_client.post(URL, payload, format="json")

    assert response.status_code == 201
    assert response.data == {"accepted": 2, "duplicates": 0}

    station = Station.objects.get(station_id="CP-TEST-0001")
    assert station.latency_ms == 180
    assert station.error_count == 1
    assert station.hygiene_score is not None
    assert HealthReport.objects.filter(station=station).count() == 2


def test_duplicate_report_across_requests_is_counted_not_stored(api_client, now):
    payload = report_payload(base_time=now)
    api_client.post(URL, payload, format="json")

    response = api_client.post(URL, payload, format="json")

    assert response.status_code == 201
    assert response.data == {"accepted": 0, "duplicates": 1}
    assert HealthReport.objects.filter(station_id="CP-TEST-0001").count() == 1


def test_duplicate_within_one_batch_is_counted_not_stored(api_client, now):
    single = report_payload(base_time=now)
    payload = [single, dict(single)]

    response = api_client.post(URL, payload, format="json")

    assert response.status_code == 201
    assert response.data == {"accepted": 1, "duplicates": 1}
    assert HealthReport.objects.filter(station_id="CP-TEST-0001").count() == 1


def test_invalid_item_in_batch_returns_400_with_index_keyed_details_and_stores_nothing(
    api_client, now
):
    payload = [
        report_payload(base_time=now, minutes_ago=1, station_id="CP-A"),
        report_payload(base_time=now, minutes_ago=0, station_id="CP-B", latency_ms=-5),
    ]

    response = api_client.post(URL, payload, format="json")

    assert response.status_code == 400
    body = response.data["error"]
    assert body["code"] == "validation_error"
    assert set(body["details"].keys()) == {"1"}
    assert "latency_ms" in body["details"]["1"]
    assert not HealthReport.objects.exists()
    assert not Station.objects.exists()


def test_unknown_field_returns_400(api_client, now):
    payload = report_payload(base_time=now)
    payload["latencyMs"] = 100

    response = api_client.post(URL, payload, format="json")

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"


def test_naive_timestamp_returns_400(api_client, now):
    payload = report_payload(base_time=now)
    payload["timestamp"] = now.replace(tzinfo=None).isoformat()

    response = api_client.post(URL, payload, format="json")

    assert response.status_code == 400


def test_future_timestamp_beyond_skew_returns_400(api_client, now):
    payload = report_payload(timestamp=now + timedelta(days=2))

    response = api_client.post(URL, payload, format="json")

    assert response.status_code == 400


def test_too_old_timestamp_returns_400(api_client, now):
    payload = report_payload(timestamp=now - timedelta(days=40))

    response = api_client.post(URL, payload, format="json")

    assert response.status_code == 400


def test_negative_error_count_returns_400(api_client, now):
    payload = report_payload(base_time=now)
    payload["error_count"] = -1

    response = api_client.post(URL, payload, format="json")

    assert response.status_code == 400


def test_bad_connectivity_status_returns_400(api_client, now):
    payload = report_payload(base_time=now)
    payload["connectivity_status"] = "flaky"

    response = api_client.post(URL, payload, format="json")

    assert response.status_code == 400


def test_batch_over_max_size_returns_400_batch_too_large(api_client, now):
    payload = [
        report_payload(base_time=now, minutes_ago=i, station_id="CP-BULK") for i in range(501)
    ]

    response = api_client.post(URL, payload, format="json")

    assert response.status_code == 400
    assert response.data["error"]["code"] == "batch_too_large"


def test_non_json_content_type_returns_415(api_client):
    response = api_client.post(URL, data="not json", content_type="text/plain")

    assert response.status_code == 415
    assert response.data["error"]["code"] == "unsupported_media_type"


def test_malformed_json_returns_400(api_client):
    response = api_client.post(URL, data="{not valid json", content_type="application/json")

    assert response.status_code == 400
    assert response.data["error"]["code"] == "malformed_json"


def test_out_of_order_report_is_stored_but_does_not_overwrite_latest_fields(api_client, now):
    api_client.post(
        URL, report_payload(base_time=now, minutes_ago=0, latency_ms=100), format="json"
    )

    late_arrival = report_payload(base_time=now, minutes_ago=5, latency_ms=999)
    response = api_client.post(URL, late_arrival, format="json")

    assert response.status_code == 201
    assert response.data["accepted"] == 1
    station = Station.objects.get(station_id="CP-TEST-0001")
    assert station.latency_ms == 100  # unchanged: the late report is older
    assert HealthReport.objects.filter(station=station).count() == 2


def test_region_is_set_once_and_never_changes(api_client, now):
    api_client.post(
        URL, report_payload(base_time=now, minutes_ago=1, region="North"), format="json"
    )
    api_client.post(
        URL, report_payload(base_time=now, minutes_ago=0, region="South"), format="json"
    )

    station = Station.objects.get(station_id="CP-TEST-0001")
    assert station.region == "North"


def test_poor_report_flags_the_station(api_client, now):
    response = api_client.post(
        URL,
        report_payload(base_time=now, connectivity_status="offline", error_count=50, latency_ms=0),
        format="json",
    )

    assert response.status_code == 201
    station = Station.objects.get(station_id="CP-TEST-0001")
    assert station.is_poor is True
    assert station.hygiene_score < 60
