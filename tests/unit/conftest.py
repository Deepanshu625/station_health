"""Shared fixtures for unit tests (no database)."""

from __future__ import annotations

import pytest

from stations.config import ScoringConfig
from stations.services.types import ReportSnapshot

DEFAULT_CONFIG = ScoringConfig(
    weight_availability=40,
    weight_latency=25,
    weight_errors=25,
    weight_firmware=10,
    latency_full_ms=200,
    latency_zero_ms=2000,
    errors_zero_at=10,
    min_supported_firmware="2.2.0",
    unknown_firmware_factor=0.5,
    poor_threshold=60,
)


@pytest.fixture
def config() -> ScoringConfig:
    return DEFAULT_CONFIG


def make_report(
    connectivity_status: str = "online",
    latency_ms: int = 150,
    error_count: int = 0,
    firmware_version: str = "2.4.0",
) -> ReportSnapshot:
    return ReportSnapshot(
        connectivity_status=connectivity_status,
        latency_ms=latency_ms,
        error_count=error_count,
        firmware_version=firmware_version,
    )
