"""
Root URL configuration for the Sports Intelligence Platform.
"""
from django.contrib import admin
from django.urls import include, path

from sports_platform.api.views.health import HealthView, ReadinessView

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),
    # Health checks
    path("health", HealthView.as_view(), name="health"),
    path("health/ready", ReadinessView.as_view(), name="health-ready"),
    # API v1
    path("api/v1/", include("sports_platform.api.urls", namespace="api-v1")),
]

# Admin site customization
admin.site.site_header = "Sports Intelligence Platform"
admin.site.site_title = "Sports Platform Admin"
admin.site.index_title = "Platform Administration"
