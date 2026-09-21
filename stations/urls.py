"""API v1 URL routes."""

from django.urls import path

from stations.views import MetricsView, PoorHygieneView, ReportsView, StationHealthView

app_name = "stations"

urlpatterns = [
    path("reports", ReportsView.as_view(), name="reports"),
    path("stations/poor-hygiene", PoorHygieneView.as_view(), name="poor-hygiene"),
    path("stations/<str:station_id>/health", StationHealthView.as_view(), name="station-health"),
    path("metrics", MetricsView.as_view(), name="metrics"),
]
