"""Thin HTTP views. Business logic lives in stations/services/."""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import connection
from django.db.utils import OperationalError
from django.http import JsonResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from stations.exceptions import BatchTooLarge, BatchValidationError, InvalidQueryParam
from stations.serializers import ReportItemSerializer
from stations.services import metrics as metrics_service
from stations.services import queries
from stations.services.ingestion import ingest_reports
from stations.services.types import ReportIn

logger = logging.getLogger("stations.views")


def healthz(request):
    """Liveness and DB connectivity check for container orchestration."""
    logger.info("Event:healthz - health check requested")
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except OperationalError:
        logger.error("Event:healthz - database unreachable")
        return JsonResponse({"status": "unavailable", "database": "unreachable"}, status=503)
    logger.info("Event:healthz - status ok")
    return JsonResponse({"status": "ok", "database": "ok"})


def _parse_int(request: Request, name: str, default: int, minimum: int, maximum: int) -> int:
    raw = request.query_params.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise InvalidQueryParam(f"{name} must be an integer.") from exc
    if not (minimum <= value <= maximum):
        raise InvalidQueryParam(f"{name} must be between {minimum} and {maximum}.")
    return value


class ReportsView(APIView):
    """`POST /api/v1/reports`: ingest one report or a batch of up to `MAX_BATCH_SIZE`."""

    @extend_schema(
        request=ReportItemSerializer(many=True),
        responses={201: OpenApiResponse(description="Reports ingested.")},
    )
    def post(self, request):
        app_config = settings.APP_CONFIG
        payload = request.data
        items = payload if isinstance(payload, list) else [payload]
        logger.info(f"Event:ReportsView - received batch of {len(items)} report(s)")

        if len(items) == 0:
            raise BatchValidationError("Batch must contain at least 1 report.", {})
        if len(items) > app_config.max_batch_size:
            logger.warning(
                f"Event:ReportsView - batch of {len(items)} exceeds "
                f"max_batch_size={app_config.max_batch_size}"
            )
            raise BatchTooLarge(
                f"Batch of {len(items)} exceeds the maximum of {app_config.max_batch_size}."
            )

        serializer = ReportItemSerializer(data=items, many=True)
        if not serializer.is_valid():
            details = {str(i): errs for i, errs in enumerate(serializer.errors) if errs}
            message = f"{len(details)} of {len(items)} reports is invalid; nothing was stored."
            logger.warning(
                f"Event:ReportsView - {len(details)} of {len(items)} report(s) failed validation"
            )
            raise BatchValidationError(message, details)

        reports = [
            ReportIn(
                station_id=item["station_id"],
                reported_at=item["timestamp"],
                connectivity_status=item["connectivity_status"],
                latency_ms=item["latency_ms"],
                error_count=item["error_count"],
                firmware_version=item["firmware_version"],
                region=item.get("region"),
            )
            for item in serializer.validated_data
        ]

        result = ingest_reports(reports, timezone.now(), settings.SCORING_CONFIG)

        logger.info(
            f"Event:ReportsView - ingestion completed accepted={result.accepted} "
            f"duplicates={result.duplicates}",
            extra={"request_id": getattr(request, "request_id", None)},
        )
        return Response({"accepted": result.accepted, "duplicates": result.duplicates}, status=201)


class StationHealthView(APIView):
    """`GET /api/v1/stations/{station_id}/health`: latest status, score and breakdown."""

    @extend_schema(responses={200: OpenApiResponse(response=OpenApiTypes.OBJECT)})
    def get(self, request, station_id: str):
        logger.info(f"Event:StationHealthView {station_id} fetching station health")
        data = queries.get_station_health(station_id)
        return Response(data)


class PoorHygieneView(APIView):
    """`GET /api/v1/stations/poor-hygiene`: stations below the score threshold."""

    @extend_schema(
        parameters=[
            OpenApiParameter("region", OpenApiTypes.STR, required=False),
            OpenApiParameter("limit", OpenApiTypes.INT, required=False),
        ],
        responses={200: OpenApiResponse(response=OpenApiTypes.OBJECT)},
    )
    def get(self, request):
        app_config = settings.APP_CONFIG
        region = request.query_params.get("region") or None
        limit = _parse_int(
            request, "limit", app_config.default_page_size, 1, app_config.max_page_size
        )
        logger.info(
            f"Event:PoorHygieneView - listing poor-hygiene stations region={region} limit={limit}"
        )
        data = queries.list_poor_hygiene(region=region, limit=limit)
        return Response(data)


class MetricsView(APIView):
    """`GET /api/v1/metrics`: fleet aggregates, optionally grouped by region."""

    @extend_schema(
        parameters=[
            OpenApiParameter("group_by", OpenApiTypes.STR, required=False, enum=["region"]),
        ],
        responses={200: OpenApiResponse(response=OpenApiTypes.OBJECT)},
    )
    def get(self, request):
        group_by = request.query_params.get("group_by") or None
        if group_by not in (None, "region"):
            raise InvalidQueryParam("group_by must be 'region'.")
        logger.info(f"Event:MetricsView - computing metrics group_by={group_by}")
        data = metrics_service.get_metrics(group_by)
        return Response(data)
