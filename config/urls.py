"""Root URL configuration."""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from stations.views import healthz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("api/v1/", include("stations.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("dashboard/", include("dashboard.urls")),
]
