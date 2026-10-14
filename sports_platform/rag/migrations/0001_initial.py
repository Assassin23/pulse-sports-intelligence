import django.db.models.deletion
import uuid
from django.db import migrations, models
import django.contrib.postgres.indexes

try:
    from pgvector.django import VectorExtension, VectorField, HnswIndex
    has_pgvector = True
except (ImportError, ModuleNotFoundError):
    has_pgvector = False
    VectorExtension = None
    VectorField = None
    HnswIndex = None


def get_migration_vector_field():
    if has_pgvector and VectorField is not None:
        return VectorField(blank=True, dimensions=1536, null=True)
    return models.JSONField(blank=True, default=list, null=True)


def get_migration_indexes():
    indexes = [
        models.Index(fields=["document", "chunk_index"], name="idx_rag_chunks_doc_idx"),
        django.contrib.postgres.indexes.GinIndex(fields=["metadata"], name="idx_rag_chunks_metadata"),
    ]
    if has_pgvector and HnswIndex is not None:
        indexes.append(
            HnswIndex(
                ef_construction=64,
                fields=["embedding"],
                m=16,
                name="idx_rag_chunks_embedding",
                opclasses=["vector_cosine_ops"],
            )
        )
    return indexes


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("sports", "0001_initial"),
    ]

    operations = [
        # In PostgreSQL, enable vector extension if pgvector is present
        *( [VectorExtension()] if (has_pgvector and VectorExtension is not None) else [
            migrations.RunSQL(
                "CREATE EXTENSION IF NOT EXISTS vector;",
                reverse_sql="DROP EXTENSION IF EXISTS vector;",
            )
        ] ),
        migrations.CreateModel(
            name="RAGDocument",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("title", models.CharField(max_length=500)),
                ("source_url", models.CharField(blank=True, max_length=1000)),
                (
                    "document_type",
                    models.CharField(
                        choices=[
                            ("team_profile", "Team Profile"),
                            ("player_profile", "Player Profile"),
                            ("competition_rules", "Competition Rules"),
                            ("article", "Article"),
                            ("terminology", "Terminology"),
                            ("h2h_history", "H2H History"),
                        ],
                        max_length=50,
                    ),
                ),
                ("entity_type", models.CharField(blank=True, max_length=20)),
                ("entity_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("content_hash", models.CharField(db_index=True, max_length=64, unique=True)),
                ("raw_content", models.TextField()),
                ("language", models.CharField(default="en", max_length=10)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("ingested_at", models.DateTimeField(auto_now_add=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "sport",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="rag_documents",
                        to="sports.sport",
                    ),
                ),
            ],
            options={
                "db_table": "rag_documents",
                "ordering": ["-ingested_at"],
                "indexes": [
                    models.Index(
                        fields=["document_type", "sport"],
                        name="idx_rag_docs_type_sport",
                    ),
                    models.Index(
                        fields=["entity_type", "entity_id"],
                        name="idx_rag_docs_entity",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="RAGChunk",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("chunk_index", models.IntegerField()),
                ("content", models.TextField()),
                ("token_count", models.IntegerField(blank=True, null=True)),
                ("embedding", get_migration_vector_field()),
                ("metadata", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunks",
                        to="rag.ragdocument",
                    ),
                ),
            ],
            options={
                "db_table": "rag_chunks",
                "ordering": ["document", "chunk_index"],
                "unique_together": {("document", "chunk_index")},
                "indexes": get_migration_indexes(),
            },
        ),
    ]
