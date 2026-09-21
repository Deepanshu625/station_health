"""Domain types shared by the pure scoring module and the services that call it.

Plain dataclasses only: no Django imports, so `scoring.py` stays a pure
function module that can be unit-tested without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ReportSnapshot:
    """The fields a score is computed from: one station's most recent report."""

    connectivity_status: str
    latency_ms: int
    error_count: int
    firmware_version: str


@dataclass(frozen=True)
class ComponentScore:
    """One weighted component of the score, plus the facts that explain it."""

    name: str
    points: float
    max: int
    detail: dict


@dataclass(frozen=True)
class ScoreResult:
    """The outcome of scoring one report."""

    score: float
    is_poor: bool
    components: tuple[ComponentScore, ...]


@dataclass(frozen=True)
class ReportIn:
    """One validated report, ready to hand to the ingestion service."""

    station_id: str
    reported_at: datetime
    connectivity_status: str
    latency_ms: int
    error_count: int
    firmware_version: str
    region: str | None = None


@dataclass(frozen=True)
class IngestResult:
    """The outcome of ingesting one batch of reports."""

    accepted: int
    duplicates: int
