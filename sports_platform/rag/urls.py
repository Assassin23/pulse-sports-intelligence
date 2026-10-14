"""
RAG User/Client URLs — Milestone 9.
Routes under /api/v1/rag/
"""
from django.urls import path
from sports_platform.rag.views import RAGSearchView, AdminRAGIngestView

app_name = "rag"

urlpatterns = [
    path("search/", RAGSearchView.as_view(), name="search"),
    path("ingest/", AdminRAGIngestView.as_view(), name="ingest"),
]
