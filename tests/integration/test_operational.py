"""Integration tests for operational endpoints."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def test_healthz_returns_200_when_database_reachable(api_client):
    response = api_client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_dashboard_renders_with_refresh_interval_attribute(api_client):
    response = api_client.get("/dashboard/")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-refresh-seconds="30"' in content


def test_openapi_schema_is_valid(api_client):
    from django.core.management import call_command

    call_command("spectacular", "--validate", "--fail-on-warn", "--file", "/dev/null")
