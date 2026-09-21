"""Pure network hygiene scoring. No Django imports, no DB access, no `now()`.

The score is a deterministic function of one station's most recent report,
which is what makes it unit-testable in isolation. Four weighted components
(0-1 each) are combined: availability, latency, errors, firmware.
"""

from __future__ import annotations

from collections.abc import Sequence

from packaging.version import InvalidVersion, Version

from stations.config import ScoringConfig
from stations.services.types import ComponentScore, ReportSnapshot, ScoreResult


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def compute_score(report: ReportSnapshot, config: ScoringConfig) -> ScoreResult:
    """Computes a `ScoreResult` from a single report."""
    is_online = report.connectivity_status == "online"

    availability_factor = 1.0 if is_online else 0.0
    availability = ComponentScore(
        name="availability",
        points=round(config.weight_availability * availability_factor, 2),
        max=config.weight_availability,
        detail={"connectivity_status": report.connectivity_status},
    )

    # Latency can't be measured meaningfully while offline, so it scores zero.
    if is_online:
        latency_factor = _clamp(
            (config.latency_zero_ms - report.latency_ms)
            / (config.latency_zero_ms - config.latency_full_ms)
        )
    else:
        latency_factor = 0.0
    latency = ComponentScore(
        name="latency",
        points=round(config.weight_latency * latency_factor, 2),
        max=config.weight_latency,
        detail={"latency_ms": report.latency_ms if is_online else None},
    )

    errors_factor = _clamp(1 - report.error_count / config.errors_zero_at)
    errors = ComponentScore(
        name="errors",
        points=round(config.weight_errors * errors_factor, 2),
        max=config.weight_errors,
        detail={"error_count": report.error_count},
    )

    firmware_factor, firmware_status = _firmware_factor(report.firmware_version, config)
    firmware = ComponentScore(
        name="firmware",
        points=round(config.weight_firmware * firmware_factor, 2),
        max=config.weight_firmware,
        detail={
            "version": report.firmware_version,
            "minimum": config.min_supported_firmware,
            "status": firmware_status,
        },
    )

    total = round(
        config.weight_availability * availability_factor
        + config.weight_latency * latency_factor
        + config.weight_errors * errors_factor
        + config.weight_firmware * firmware_factor,
        2,
    )
    return ScoreResult(
        score=total,
        is_poor=total < config.poor_threshold,
        components=(availability, latency, errors, firmware),
    )


def _firmware_factor(version: str, config: ScoringConfig) -> tuple[float, str]:
    try:
        parsed = Version(version)
    except InvalidVersion:
        return config.unknown_firmware_factor, "unknown"
    minimum = Version(config.min_supported_firmware)
    if parsed >= minimum:
        return 1.0, "supported"
    return 0.0, "outdated"


def serialize_components(components: Sequence[ComponentScore]) -> dict:
    """Flattens components into the `score_components` JSON shape stored on `Station`."""
    return {
        component.name: {"points": component.points, "max": component.max, **component.detail}
        for component in components
    }
