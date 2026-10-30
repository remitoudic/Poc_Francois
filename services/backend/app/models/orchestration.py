"""v2 data model: Order → Position → Workflow → Tasks (backend-architecture.md §3).

Temporal owns execution state; these tables are the read model the UI and analytics use.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base
from app.domain.enums import Destination, OrderStatus, TaskStatus, WorkflowStatus


class Customer(Base):
    """Cache of Plunet customers."""

    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    plunet_id = Column(Integer, unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    synced_at = Column(DateTime, default=datetime.utcnow)


class Resource(Base):
    """Cache of Plunet resources (project managers, translators)."""

    __tablename__ = "resources"

    id = Column(Integer, primary_key=True)
    plunet_id = Column(Integer, unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    synced_at = Column(DateTime, default=datetime.utcnow)


class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    tasks = Column(JSONB, nullable=False)  # ordered list of TaskType values


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    kind = Column(String(10), nullable=False)  # OrderKind
    status = Column(String(30), nullable=False, default=OrderStatus.DRAFT, index=True)
    number = Column(String(50), nullable=True)  # Plunet order/quote number
    title = Column(String(255), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    pm_resource_id = Column(Integer, ForeignKey("resources.id"), nullable=True, index=True)
    plunet_order_id = Column(Integer, nullable=True)
    plunet_quote_id = Column(Integer, nullable=True)
    deadline = Column(DateTime, nullable=True)
    template_id = Column(Integer, ForeignKey("workflow_templates.id"), nullable=False)
    default_destination = Column(String(20), nullable=False, default=Destination.POLYLANG)
    destination_url = Column(String(512), nullable=True)
    source_site = Column(String(255), nullable=True)
    source_lang = Column(String(20), nullable=False)
    temporal_workflow_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    customer = relationship("Customer")
    pm = relationship("Resource")
    template = relationship("WorkflowTemplate")
    positions = relationship(
        "Position", back_populates="order", cascade="all, delete-orphan", order_by="Position.no"
    )


class Position(Base):
    """One post × one target language = one .xliff (Plunet item)."""

    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("order_id", "no"),)

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    no = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    polylang_post_id = Column(Integer, nullable=True)
    source_lang = Column(String(20), nullable=False)
    target_lang = Column(String(20), nullable=False)
    plunet_item_id = Column(Integer, nullable=True)
    xliff_raw = Column(Text, nullable=True)
    xliff_processed = Column(Text, nullable=True)
    words = Column(Integer, default=0, nullable=False)
    segments = Column(Integer, default=0, nullable=False)
    destination = Column(String(20), nullable=False, default=Destination.POLYLANG)
    destination_url = Column(String(512), nullable=True)
    status = Column(String(20), nullable=False, default=WorkflowStatus.NOT_STARTED)
    temporal_workflow_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    order = relationship("Order", back_populates="positions")
    tasks = relationship(
        "Task", back_populates="position", cascade="all, delete-orphan", order_by="Task.seq"
    )


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("position_id", "seq"),)

    id = Column(Integer, primary_key=True)
    position_id = Column(Integer, ForeignKey("positions.id", ondelete="CASCADE"), nullable=False)
    seq = Column(Integer, nullable=False)
    type = Column(String(20), nullable=False)  # TaskType
    status = Column(String(20), nullable=False, default=TaskStatus.PENDING)
    overlay = Column(String(20), nullable=True)  # Overlay
    plunet_job_id = Column(Integer, nullable=True, index=True)
    plunet_job_status = Column(String(30), nullable=True)  # raw Plunet JobStatus name
    assignee_resource_id = Column(Integer, ForeignKey("resources.id"), nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    cost = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(3), nullable=True)
    findings = Column(JSONB, nullable=True)  # QA findings of the last run
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    position = relationship("Position", back_populates="tasks")
    assignee = relationship("Resource")


class Event(Base):
    """Event bus + audit log. Each insert is announced on NOTIFY fox_events by a trigger."""

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_order_id_id", "order_id", "id"),
        Index("ix_events_position_id_id", "position_id", "id"),
    )

    id = Column(BigInteger, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    kind = Column(String(10), nullable=False)  # EventKind
    level = Column(String(10), nullable=False)  # EventLevel
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=True)
    position_id = Column(Integer, ForeignKey("positions.id", ondelete="CASCADE"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    actor = Column(String(100), nullable=False, default="system")
    message = Column(Text, nullable=False)
    reason = Column(Text, nullable=True)
    data = Column(JSONB, nullable=True)
