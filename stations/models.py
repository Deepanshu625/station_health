"""ORM models for the latest-state table and the append-only report history.

The ORM is only used from services; views and serializers never touch it
directly.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q


class Connectivity(models.TextChoices):
    ONLINE = "online"
    OFFLINE = "offline"


class Station(models.Model):
    """Latest known state for one station, derived from its most recent report."""

    station_id = models.CharField(primary_key=True, max_length=64)
    region = models.CharField(max_length=32, default="unassigned", db_index=True)

    last_reported_at = models.DateTimeField(null=True, db_index=True)
    connectivity_status = models.CharField(max_length=8, choices=Connectivity.choices, null=True)
    latency_ms = models.PositiveIntegerField(null=True)
    error_count = models.PositiveIntegerField(null=True)
    firmware_version = models.CharField(max_length=32, null=True)

    hygiene_score = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    score_components = models.JSONField(null=True)
    is_poor = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stations"
        constraints = [
            models.CheckConstraint(
                condition=Q(hygiene_score__gte=0) & Q(hygiene_score__lte=100),
                name="stations_score_range",
            ),
        ]

    def __str__(self) -> str:
        return self.station_id


class HealthReport(models.Model):
    """Append-only report history, persisted as received."""

    id = models.BigAutoField(primary_key=True)
    station = models.ForeignKey(
        Station, on_delete=models.CASCADE, db_column="station_id", related_name="reports"
    )
    reported_at = models.DateTimeField()
    received_at = models.DateTimeField()
    connectivity_status = models.CharField(max_length=8, choices=Connectivity.choices)
    latency_ms = models.PositiveIntegerField()
    error_count = models.PositiveIntegerField()
    firmware_version = models.CharField(max_length=32)

    class Meta:
        db_table = "health_reports"
        constraints = [
            models.UniqueConstraint(
                fields=["station", "reported_at"], name="uniq_station_reported_at"
            ),
            models.CheckConstraint(
                condition=Q(connectivity_status__in=["online", "offline"]),
                name="reports_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.station_id} @ {self.reported_at.isoformat()}"
