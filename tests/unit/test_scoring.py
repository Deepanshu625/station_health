"""Unit tests for the pure scoring module. No database needed."""

from __future__ import annotations

from stations.services.scoring import compute_score, serialize_components

from .conftest import make_report


def component(result, name):
    return next(c for c in result.components if c.name == name)


class TestComputeScoreHappyPaths:
    def test_all_online_no_errors_supported_firmware_scores_100(self, config):
        result = compute_score(make_report(), config)
        assert result.score == 100.0
        assert result.is_poor is False

    def test_offline_gives_zero_availability_and_zero_latency(self, config):
        result = compute_score(make_report(connectivity_status="offline"), config)
        assert component(result, "availability").points == 0.0
        assert component(result, "latency").points == 0.0
        assert component(result, "latency").detail["latency_ms"] is None


class TestLatencyBoundaries:
    def test_latency_at_full_threshold_earns_full_points(self, config):
        result = compute_score(make_report(latency_ms=200), config)
        assert component(result, "latency").points == 25.0

    def test_latency_at_zero_threshold_earns_zero_points(self, config):
        result = compute_score(make_report(latency_ms=2000), config)
        assert component(result, "latency").points == 0.0

    def test_latency_at_midpoint_earns_exactly_half_points(self, config):
        result = compute_score(make_report(latency_ms=1100), config)
        assert component(result, "latency").points == 12.5


class TestErrors:
    def test_errors_at_or_above_zero_at_earns_zero_points(self, config):
        result = compute_score(make_report(error_count=10), config)
        assert component(result, "errors").points == 0.0

    def test_errors_linear_between_zero_and_zero_at(self, config):
        result = compute_score(make_report(error_count=5), config)
        assert component(result, "errors").points == 12.5


class TestFirmware:
    def test_supported_firmware_earns_full_points(self, config):
        result = compute_score(make_report(firmware_version="2.2.0"), config)
        assert component(result, "firmware").points == 10.0
        assert component(result, "firmware").detail["status"] == "supported"

    def test_outdated_firmware_earns_zero_points(self, config):
        result = compute_score(make_report(firmware_version="1.9.0"), config)
        assert component(result, "firmware").points == 0.0
        assert component(result, "firmware").detail["status"] == "outdated"

    def test_unparseable_firmware_earns_half_points(self, config):
        result = compute_score(make_report(firmware_version="not-a-version"), config)
        assert component(result, "firmware").points == 5.0
        assert component(result, "firmware").detail["status"] == "unknown"


class TestPoorThreshold:
    def test_score_just_below_threshold_is_poor(self, config):
        # availability 40 + latency 2.49 + errors 7.5 + firmware 10 = 59.99.
        result = compute_score(
            make_report(latency_ms=1821, error_count=7, firmware_version="2.2.0"), config
        )
        assert result.score == 59.99
        assert result.is_poor is True

    def test_score_at_exactly_threshold_is_not_poor(self, config):
        # availability 40 + latency 20 (560ms) + errors 0 + firmware 0 (outdated) = 60.00.
        result = compute_score(
            make_report(latency_ms=560, error_count=10, firmware_version="1.0.0"), config
        )
        assert result.score == 60.0
        assert result.is_poor is False


class TestSerializeComponents:
    def test_flattens_points_max_and_detail(self, config):
        result = compute_score(make_report(), config)
        serialized = serialize_components(result.components)
        assert serialized["availability"]["points"] == 40.0
        assert serialized["availability"]["max"] == 40
        assert serialized["availability"]["connectivity_status"] == "online"
