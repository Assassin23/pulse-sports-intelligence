"""
RAG Admin URLs — Milestone 9.
Routes under /api/v1/admin/rag/
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from sports_platform.rag.views import AdminRAGIngestView, AdminRAGDocumentViewSet

app_name = "admin-rag"

router = DefaultRouter()
router.register(r"documents", AdminRAGDocumentViewSet, basename="admin-documents")

urlpatterns = [
    path("ingest", AdminRAGIngestView.as_view(), name="admin-ingest-no-slash"),
    path("ingest/", AdminRAGIngestView.as_view(), name="admin-ingest"),
    path("", include(router.urls)),
]
