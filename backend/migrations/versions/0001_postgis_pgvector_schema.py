"""Create the SANKET PostGIS, evidence, telemetry, and vector schema.

Revision ID: 0001_postgis_pgvector
Revises:
"""

from alembic import op

from backend.app.models import Base

revision = "0001_postgis_pgvector"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=op.get_bind())
    op.execute("UPDATE wells SET location=ST_SetSRID(ST_MakePoint(longitude,latitude),4326)::geography WHERE location IS NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_document_chunks_fts ON document_chunks USING gin (to_tsvector('simple', content))")
    op.execute("CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_hnsw ON document_chunks USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_document_chunks_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS idx_document_chunks_fts")
    Base.metadata.drop_all(bind=op.get_bind())
