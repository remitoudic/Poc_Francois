"""v2 orchestration model + realtime events bus.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Small payload (ids only): NOTIFY is limited to 8000 bytes and delivered only on commit.
NOTIFY_FUNCTION = """
CREATE OR REPLACE FUNCTION notify_event() RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify('fox_events', json_build_object(
    'id', NEW.id,
    'kind', NEW.kind,
    'level', NEW.level,
    'order_id', NEW.order_id,
    'position_id', NEW.position_id,
    'task_id', NEW.task_id
  )::text);
  RETURN NEW;
END
$$ LANGUAGE plpgsql;
"""

NOTIFY_TRIGGER = """
CREATE TRIGGER events_notify AFTER INSERT ON events
FOR EACH ROW EXECUTE FUNCTION notify_event();
"""

TEMPLATES = [
    ("standard", "Standard", ["IMPORT", "PM", "TRA", "REV", "QA", "DELIVER"]),
    ("light", "Light", ["IMPORT", "TRA", "QA", "DELIVER"]),
    ("regulated", "Regulated", ["IMPORT", "PM", "TRA", "REV", "REV", "QA", "DELIVER"]),
]


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("plunet_id", sa.Integer, nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("synced_at", sa.DateTime),
    )
    op.create_table(
        "resources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("plunet_id", sa.Integer, nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("synced_at", sa.DateTime),
    )
    templates = op.create_table(
        "workflow_templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("tasks", JSONB, nullable=False),
    )
    op.bulk_insert(templates, [{"code": c, "name": n, "tasks": t} for c, n, t in TEMPLATES])

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("number", sa.String(50)),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id")),
        sa.Column("pm_resource_id", sa.Integer, sa.ForeignKey("resources.id"), index=True),
        sa.Column("plunet_order_id", sa.Integer),
        sa.Column("plunet_quote_id", sa.Integer),
        sa.Column("deadline", sa.DateTime),
        sa.Column(
            "template_id", sa.Integer, sa.ForeignKey("workflow_templates.id"), nullable=False
        ),
        sa.Column("default_destination", sa.String(20), nullable=False),
        sa.Column("destination_url", sa.String(512)),
        sa.Column("source_site", sa.String(255)),
        sa.Column("source_lang", sa.String(20), nullable=False),
        sa.Column("temporal_workflow_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "order_id", sa.Integer, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("no", sa.Integer, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("polylang_post_id", sa.Integer),
        sa.Column("source_lang", sa.String(20), nullable=False),
        sa.Column("target_lang", sa.String(20), nullable=False),
        sa.Column("plunet_item_id", sa.Integer),
        sa.Column("xliff_raw", sa.Text),
        sa.Column("xliff_processed", sa.Text),
        sa.Column("words", sa.Integer, nullable=False, server_default="0"),
        sa.Column("segments", sa.Integer, nullable=False, server_default="0"),
        sa.Column("destination", sa.String(20), nullable=False),
        sa.Column("destination_url", sa.String(512)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("temporal_workflow_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("order_id", "no"),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "position_id",
            sa.Integer,
            sa.ForeignKey("positions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("overlay", sa.String(20)),
        sa.Column("plunet_job_id", sa.Integer, index=True),
        sa.Column("plunet_job_status", sa.String(30)),
        sa.Column("assignee_resource_id", sa.Integer, sa.ForeignKey("resources.id")),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("findings", JSONB),
        sa.Column("error", sa.Text),
        sa.Column("started_at", sa.DateTime),
        sa.Column("finished_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("position_id", "seq"),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id", ondelete="CASCADE")),
        sa.Column("position_id", sa.Integer, sa.ForeignKey("positions.id", ondelete="CASCADE")),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("actor", sa.String(100), nullable=False, server_default="system"),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("data", JSONB),
    )
    op.create_index("ix_events_order_id_id", "events", ["order_id", "id"])
    op.create_index("ix_events_position_id_id", "events", ["position_id", "id"])
    op.execute(NOTIFY_FUNCTION)
    op.execute(NOTIFY_TRIGGER)

    # v1 segments are re-linked to positions; job_id becomes optional.
    op.add_column(
        "xliff_segments",
        sa.Column("position_id", sa.Integer, sa.ForeignKey("positions.id", ondelete="CASCADE")),
    )
    op.create_index("ix_xliff_segments_position_id", "xliff_segments", ["position_id"])
    op.alter_column("xliff_segments", "job_id", nullable=True)


def downgrade() -> None:
    op.alter_column("xliff_segments", "job_id", nullable=False)
    op.drop_index("ix_xliff_segments_position_id", "xliff_segments")
    op.drop_column("xliff_segments", "position_id")
    op.execute("DROP TRIGGER IF EXISTS events_notify ON events")
    op.execute("DROP FUNCTION IF EXISTS notify_event()")
    op.drop_table("events")
    op.drop_table("tasks")
    op.drop_table("positions")
    op.drop_table("orders")
    op.drop_table("workflow_templates")
    op.drop_table("resources")
    op.drop_table("customers")
