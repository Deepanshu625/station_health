"""Thin view for the dashboard shell; all data comes from the public REST API."""

from __future__ import annotations

from django.conf import settings
from django.views.generic import TemplateView


class DashboardView(TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["refresh_seconds"] = settings.DASHBOARD_REFRESH_SECONDS
        return context
