"""Report ingestion: persist history, then upsert the station's latest state and score."""

from __future__ import annotations

import logging
from datetime import datetime

from django.db import IntegrityError, transaction

from stations.config import ScoringConfig
from stations.models import HealthReport, Station
from stations.services import scoring
from stations.services.types import IngestResult, ReportIn, ReportSnapshot

logger = logging.getLogger("stations.ingestion")


def ingest_reports(
    reports: list[ReportIn], received_at: datetime, config: ScoringConfig
) -> IngestResult:
    """Stores each report and recomputes its station's latest state and score."""
    logger.info(f"Event:ingest_reports - processing {len(reports)} report(s)")
    accepted = 0
    duplicates = 0
    for report in reports:
        if _ingest_one(report, received_at, config):
            accepted += 1
        else:
            duplicates += 1
    logger.info(f"Event:ingest_reports - completed accepted={accepted} duplicates={duplicates}")
    return IngestResult(accepted=accepted, duplicates=duplicates)


def _ingest_one(report: ReportIn, received_at: datetime, config: ScoringConfig) -> bool:
    """Returns True if newly stored, False if it was a duplicate (station_id, reported_at)."""
    with transaction.atomic():
        station, _ = Station.objects.get_or_create(
            station_id=report.station_id,
            defaults={"region": report.region or "unassigned"},
        )
        # Lock the row so concurrent reports for this station serialize here.
        station = Station.objects.select_for_update().get(pk=station.pk)
        if station.region == "unassigned" and report.region:
            station.region = report.region

        try:
            with transaction.atomic():
                HealthReport.objects.create(
                    station=station,
                    reported_at=report.reported_at,
                    received_at=received_at,
                    connectivity_status=report.connectivity_status,
                    latency_ms=report.latency_ms,
                    error_count=report.error_count,
                    firmware_version=report.firmware_version,
                )
        except IntegrityError:
            logger.info(
                f"Event:ingest_reports {report.station_id} duplicate report ignored "
                f"reported_at={report.reported_at.isoformat()}"
            )
            return False

        # A late-arriving report shouldn't make the station look like it went
        # back in time, so only the newest report updates the latest state.
        if station.last_reported_at is None or report.reported_at >= station.last_reported_at:
            result = scoring.compute_score(
                ReportSnapshot(
                    connectivity_status=report.connectivity_status,
                    latency_ms=report.latency_ms,
                    error_count=report.error_count,
                    firmware_version=report.firmware_version,
                ),
                config,
            )
            station.last_reported_at = report.reported_at
            station.connectivity_status = report.connectivity_status
            station.latency_ms = report.latency_ms
            station.error_count = report.error_count
            station.firmware_version = report.firmware_version
            station.hygiene_score = result.score
            station.score_components = scoring.serialize_components(result.components)
            station.is_poor = result.is_poor

        station.save()

    logger.info(
        f"Event:ingest_reports {report.station_id} report accepted "
        f"reported_at={report.reported_at.isoformat()}"
    )
    return True
