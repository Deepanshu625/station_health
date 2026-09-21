"""Read queries for the API. The ORM is only used here and in `metrics.py`;
views and serializers never touch it.
"""

from __future__ import annotations

import logging

from stations.exceptions import StationNotFound
from stations.models import Station

logger = logging.getLogger("stations.queries")


def _num(value) -> float | None:
    """Converts a nullable `Decimal` to `float` for JSON responses."""
    return float(value) if value is not None else None


def get_station_or_404(station_id: str) -> Station:
    try:
        return Station.objects.get(station_id=station_id)
    except Station.DoesNotExist as exc:
        logger.warning(f"Event:get_station_health {station_id} station not found")
        raise StationNotFound(f"Station {station_id!r} not found.") from exc


def get_station_health(station_id: str) -> dict:
    station = get_station_or_404(station_id)
    logger.info(f"Event:get_station_health {station_id} station health retrieved")
    return {
        "station_id": station.station_id,
        "region": station.region,
        "connectivity_status": station.connectivity_status,
        "latency_ms": station.latency_ms,
        "error_count": station.error_count,
        "firmware_version": station.firmware_version,
        "last_reported_at": station.last_reported_at,
        "hygiene_score": _num(station.hygiene_score),
        "is_poor": station.is_poor,
        "score_components": station.score_components,
    }


def list_poor_hygiene(*, region: str | None, limit: int) -> dict:
    qs = Station.objects.filter(is_poor=True)
    if region:
        qs = qs.filter(region=region)

    total = qs.count()
    rows = qs.order_by("hygiene_score", "station_id")[:limit]
    logger.info(f"Event:list_poor_hygiene - region={region} limit={limit} results={total}")

    results = [
        {
            "station_id": station.station_id,
            "region": station.region,
            "hygiene_score": _num(station.hygiene_score),
            "connectivity_status": station.connectivity_status,
            "last_reported_at": station.last_reported_at,
        }
        for station in rows
    ]
    return {"results": results, "count": total}
