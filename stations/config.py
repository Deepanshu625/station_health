"""Immutable, validated configuration for scoring and API behaviour.

Kept separate from ``settings.py`` so ``scoring.py`` and the services layer
depend on plain dataclasses instead of Django's settings machinery, and so
config can be constructed and validated in tests without touching Django.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from packaging.version import InvalidVersion, Version

UNKNOWN_FIRMWARE_FACTOR = 0.5


@dataclass(frozen=True)
class ScoringConfig:
    """Parameters for the network hygiene score formula."""

    weight_availability: int
    weight_latency: int
    weight_errors: int
    weight_firmware: int
    latency_full_ms: int
    latency_zero_ms: int
    errors_zero_at: int
    min_supported_firmware: str
    unknown_firmware_factor: float
    poor_threshold: float


@dataclass(frozen=True)
class AppConfig:
    """Parameters for ingestion and the read API's pagination."""

    max_batch_size: int
    max_clock_skew_seconds: int
    max_report_age_days: int
    default_page_size: int
    max_page_size: int
    dashboard_refresh_seconds: int


class ConfigError(Exception):
    """Raised when configuration fails validation at startup."""


def _int_env(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float_env(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def load_scoring_config() -> ScoringConfig:
    """Build a `ScoringConfig` from environment variables."""
    return ScoringConfig(
        weight_availability=_int_env("WEIGHT_AVAILABILITY", 40),
        weight_latency=_int_env("WEIGHT_LATENCY", 25),
        weight_errors=_int_env("WEIGHT_ERRORS", 25),
        weight_firmware=_int_env("WEIGHT_FIRMWARE", 10),
        latency_full_ms=_int_env("LATENCY_FULL_MS", 200),
        latency_zero_ms=_int_env("LATENCY_ZERO_MS", 2000),
        errors_zero_at=_int_env("ERRORS_ZERO_AT", 10),
        min_supported_firmware=os.environ.get("MIN_SUPPORTED_FIRMWARE", "2.2.0"),
        unknown_firmware_factor=UNKNOWN_FIRMWARE_FACTOR,
        poor_threshold=_float_env("POOR_THRESHOLD", 60),
    )


def load_app_config() -> AppConfig:
    """Build an `AppConfig` from environment variables."""
    return AppConfig(
        max_batch_size=_int_env("MAX_BATCH_SIZE", 500),
        max_clock_skew_seconds=_int_env("MAX_CLOCK_SKEW_SECONDS", 86400),
        max_report_age_days=_int_env("MAX_REPORT_AGE_DAYS", 30),
        default_page_size=_int_env("DEFAULT_PAGE_SIZE", 50),
        max_page_size=_int_env("MAX_PAGE_SIZE", 200),
        dashboard_refresh_seconds=_int_env("DASHBOARD_REFRESH_SECONDS", 30),
    )


def validate_scoring_config(config: ScoringConfig) -> None:
    """Fail fast on a bad deploy rather than silently producing wrong scores."""
    weights = (
        config.weight_availability,
        config.weight_latency,
        config.weight_errors,
        config.weight_firmware,
    )
    if sum(weights) != 100:
        raise ConfigError(f"Scoring weights must sum to 100, got {sum(weights)} ({weights}).")
    if config.latency_full_ms >= config.latency_zero_ms:
        raise ConfigError(
            "LATENCY_FULL_MS must be strictly less than LATENCY_ZERO_MS "
            f"(got {config.latency_full_ms} >= {config.latency_zero_ms})."
        )
    try:
        Version(config.min_supported_firmware)
    except InvalidVersion as exc:
        raise ConfigError(
            f"MIN_SUPPORTED_FIRMWARE={config.min_supported_firmware!r} is not a parseable version."
        ) from exc
