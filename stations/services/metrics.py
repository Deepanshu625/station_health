"""Fleet-wide aggregates computed from the latest-state table."""

from __future__ import annotations

import logging

from django.db.models import Avg, Count, Q
from django.utils import timezone

from stations.models import Station

logger = logging.getLogger("stations.metrics")

_AGGREGATE_ANNOTATIONS = {
    "stations": Count("station_id"),
    "online": Count("station_id", filter=Q(connectivity_status="online")),
    "offline": Count("station_id", filter=Q(connectivity_status="offline")),
    "poor": Count("station_id", filter=Q(is_poor=True)),
    "avg_latency_ms": Avg("latency_ms", filter=Q(connectivity_status="online")),
    "avg_hygiene_score": Avg("hygiene_score"),
}


def _format_aggregate(raw: dict) -> dict:
    return {
        "stations": raw["stations"],
        "online": raw["online"],
        "offline": raw["offline"],
        "poor": raw["poor"],
        "avg_latency_ms": round(float(raw["avg_latency_ms"]), 1)
        if raw["avg_latency_ms"] is not None
        else None,
        "avg_hygiene_score": round(float(raw["avg_hygiene_score"]), 1)
        if raw["avg_hygiene_score"] is not None
        else None,
    }


def get_metrics(group_by: str | None) -> dict:
    """Computed with a single `GROUP BY` query over `stations` per group requested."""
    logger.info(f"Event:get_metrics - group_by={group_by}")
    overall = _format_aggregate(Station.objects.aggregate(**_AGGREGATE_ANNOTATIONS))

    groups = []
    if group_by == "region":
        rows = (
            Station.objects.values("region").annotate(**_AGGREGATE_ANNOTATIONS).order_by("region")
        )
        for row in rows:
            group = {"region": row["region"]}
            group.update(_format_aggregate(row))
            groups.append(group)

    logger.info(f"Event:get_metrics - computed overall stations={overall['stations']}")
    return {"generated_at": timezone.now(), "overall": overall, "groups": groups}
