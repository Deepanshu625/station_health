"""Request validation for ingestion, plus response serializers used only for the OpenAPI schema."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

STATION_ID_PATTERN = r"^[A-Za-z0-9_-]+$"
REGION_PATTERN = r"^[A-Za-z0-9 _-]+$"


class ReportItemSerializer(serializers.Serializer):
    """One health report. Unknown fields are rejected so typos fail loudly."""

    station_id = serializers.RegexField(STATION_ID_PATTERN, max_length=64)
    timestamp = serializers.CharField()
    connectivity_status = serializers.ChoiceField(choices=["online", "offline"])
    latency_ms = serializers.IntegerField(min_value=0, max_value=600_000)
    error_count = serializers.IntegerField(min_value=0, max_value=100_000)
    firmware_version = serializers.CharField(min_length=1, max_length=32)
    region = serializers.RegexField(REGION_PATTERN, max_length=32, required=False, allow_null=True)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected an object.")
        unknown = set(data.keys()) - set(self.fields.keys())
        if unknown:
            raise serializers.ValidationError(
                {field: ["Unknown field."] for field in sorted(unknown)}
            )
        return super().to_internal_value(data)

    def validate_timestamp(self, value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise serializers.ValidationError("Must be a valid ISO 8601 timestamp.") from exc
        if parsed.tzinfo is None:
            raise serializers.ValidationError("Timestamp must include a timezone offset.")
        parsed = parsed.astimezone(UTC)

        app_config = settings.APP_CONFIG
        now = timezone.now()
        max_future = now + timedelta(seconds=app_config.max_clock_skew_seconds)
        oldest_allowed = now - timedelta(days=app_config.max_report_age_days)
        if parsed > max_future:
            raise serializers.ValidationError("Timestamp is too far in the future.")
        if parsed < oldest_allowed:
            raise serializers.ValidationError("Timestamp is older than the maximum allowed age.")
        return parsed


# --- Response serializers (schema documentation only; never used to validate input) ---


class IngestResponseSerializer(serializers.Serializer):
    accepted = serializers.IntegerField()
    duplicates = serializers.IntegerField()


class AvailabilityComponentSerializer(serializers.Serializer):
    points = serializers.FloatField()
    max = serializers.IntegerField()
    connectivity_status = serializers.ChoiceField(choices=["online", "offline"])


class LatencyComponentSerializer(serializers.Serializer):
    points = serializers.FloatField()
    max = serializers.IntegerField()
    latency_ms = serializers.IntegerField(allow_null=True)


class ErrorsComponentSerializer(serializers.Serializer):
    points = serializers.FloatField()
    max = serializers.IntegerField()
    error_count = serializers.IntegerField()


class FirmwareComponentSerializer(serializers.Serializer):
    points = serializers.FloatField()
    max = serializers.IntegerField()
    version = serializers.CharField()
    minimum = serializers.CharField()
    status = serializers.ChoiceField(choices=["supported", "outdated", "unknown"])


class ScoreComponentsSerializer(serializers.Serializer):
    availability = AvailabilityComponentSerializer()
    latency = LatencyComponentSerializer()
    errors = ErrorsComponentSerializer()
    firmware = FirmwareComponentSerializer()


class StationHealthResponseSerializer(serializers.Serializer):
    station_id = serializers.CharField()
    region = serializers.CharField()
    connectivity_status = serializers.ChoiceField(
        choices=["online", "offline"], allow_null=True
    )
    latency_ms = serializers.IntegerField(allow_null=True)
    error_count = serializers.IntegerField(allow_null=True)
    firmware_version = serializers.CharField(allow_null=True)
    last_reported_at = serializers.DateTimeField(allow_null=True)
    hygiene_score = serializers.FloatField(allow_null=True)
    is_poor = serializers.BooleanField()
    score_components = ScoreComponentsSerializer(allow_null=True)


class PoorHygieneItemSerializer(serializers.Serializer):
    station_id = serializers.CharField()
    region = serializers.CharField()
    hygiene_score = serializers.FloatField(allow_null=True)
    connectivity_status = serializers.ChoiceField(
        choices=["online", "offline"], allow_null=True
    )
    last_reported_at = serializers.DateTimeField(allow_null=True)


class PoorHygieneResponseSerializer(serializers.Serializer):
    results = PoorHygieneItemSerializer(many=True)
    count = serializers.IntegerField()


class MetricsAggregateSerializer(serializers.Serializer):
    stations = serializers.IntegerField()
    online = serializers.IntegerField()
    offline = serializers.IntegerField()
    poor = serializers.IntegerField()
    avg_latency_ms = serializers.FloatField(allow_null=True)
    avg_hygiene_score = serializers.FloatField(allow_null=True)


class MetricsRegionGroupSerializer(MetricsAggregateSerializer):
    region = serializers.CharField()


class MetricsResponseSerializer(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    overall = MetricsAggregateSerializer()
    groups = MetricsRegionGroupSerializer(many=True)
