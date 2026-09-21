"""Unit tests for startup config validation."""

from __future__ import annotations

import pytest

from stations.config import ConfigError, ScoringConfig, validate_scoring_config

BASE_KWARGS = dict(
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


def make_config(**overrides) -> ScoringConfig:
    return ScoringConfig(**{**BASE_KWARGS, **overrides})


def test_valid_config_passes():
    validate_scoring_config(make_config())


def test_rejects_weights_that_do_not_sum_to_100():
    config = make_config(weight_availability=50)
    with pytest.raises(ConfigError, match="sum to 100"):
        validate_scoring_config(config)


def test_rejects_inverted_latency_bounds():
    config = make_config(latency_full_ms=2000, latency_zero_ms=200)
    with pytest.raises(ConfigError, match="LATENCY_FULL_MS"):
        validate_scoring_config(config)


def test_rejects_unparseable_firmware_minimum():
    config = make_config(min_supported_firmware="not-a-version")
    with pytest.raises(ConfigError, match="MIN_SUPPORTED_FIRMWARE"):
        validate_scoring_config(config)
