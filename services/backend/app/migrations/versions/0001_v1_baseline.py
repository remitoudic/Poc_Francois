"""v1 baseline: ETL tables that existed before Alembic (created by create_all).

Revision ID: 0001
Revises:
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())

    if "etl_jobs" not in existing:
        op.create_table(
            "etl_jobs",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("job_name", sa.String(255), nullable=False),
            sa.Column("source_type", sa.String(50), nullable=False),
            sa.Column("source_reference", sa.String(512)),
            sa.Column("status", sa.String(50), index=True),
            sa.Column("source_language", sa.String(20)),
            sa.Column("target_language", sa.String(20)),
            sa.Column("segment_count", sa.Integer),
            sa.Column("word_count", sa.Integer),
            sa.Column("plunet_synced", sa.String(50)),
            sa.Column("plunet_order_id", sa.Integer),
            sa.Column("plunet_status_message", sa.String(255)),
            sa.Column("destination_url", sa.String(512)),
            sa.Column("destination_status_code", sa.Integer),
            sa.Column("destination_response", sa.Text),
            sa.Column("raw_xliff", sa.Text),
            sa.Column("processed_xliff", sa.Text),
            sa.Column("error_message", sa.Text),
            sa.Column("created_at", sa.DateTime),
            sa.Column("updated_at", sa.DateTime),
        )

    if "xliff_segments" not in existing:
        op.create_table(
            "xliff_segments",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column(
                "job_id", sa.Integer, sa.ForeignKey("etl_jobs.id"), nullable=False, index=True
            ),
            sa.Column("unit_id", sa.String(100), nullable=False),
            sa.Column("resname", sa.String(255)),
            sa.Column("source_text", sa.Text, nullable=False),
            sa.Column("target_text", sa.Text),
            sa.Column("status", sa.String(50)),
            sa.Column("notes", sa.Text),
        )

    if "destination_deliveries" not in existing:
        op.create_table(
            "destination_deliveries",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("job_id", sa.Integer),
            sa.Column("source_filename", sa.String(255)),
            sa.Column("source_language", sa.String(20)),
            sa.Column("target_language", sa.String(20)),
            sa.Column("segment_count", sa.Integer),
            sa.Column("word_count", sa.Integer),
            sa.Column("payload_size", sa.Integer),
            sa.Column("received_at", sa.DateTime),
        )


def downgrade() -> None:
    op.drop_table("destination_deliveries")
    op.drop_table("xliff_segments")
    op.drop_table("etl_jobs")
