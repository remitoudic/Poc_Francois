from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class ETLJob(Base):
    __tablename__ = "etl_jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_name = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False)  # fixture, api, upload
    source_reference = Column(String(512), nullable=True)  # filename, url, etc.
    status = Column(String(50), default="PENDING", index=True)
    # PENDING, EXTRACTED, PARSED, PLUNET_SYNCED, DELIVERED, FAILED

    source_language = Column(String(20), default="en")
    target_language = Column(String(20), default="fr")
    segment_count = Column(Integer, default=0)
    word_count = Column(Integer, default=0)

    # Plunet integration tracking
    plunet_synced = Column(String(50), default="NOT_SYNCED")
    plunet_order_id = Column(Integer, nullable=True)
    plunet_status_message = Column(String(255), nullable=True)

    # Destination delivery tracking
    destination_url = Column(String(512), nullable=True)
    destination_status_code = Column(Integer, nullable=True)
    destination_response = Column(Text, nullable=True)

    # Payloads & errors
    raw_xliff = Column(Text, nullable=True)
    processed_xliff = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    segments = relationship("XLIFFSegment", back_populates="job", cascade="all, delete-orphan")


class XLIFFSegment(Base):
    __tablename__ = "xliff_segments"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("etl_jobs.id"), nullable=False, index=True)
    unit_id = Column(String(100), nullable=False)
    resname = Column(String(255), nullable=True)
    source_text = Column(Text, nullable=False)
    target_text = Column(Text, nullable=True)
    status = Column(String(50), default="translated")
    notes = Column(Text, nullable=True)

    job = relationship("ETLJob", back_populates="segments")


class DestinationDelivery(Base):
    __tablename__ = "destination_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, nullable=True)
    source_filename = Column(String(255), nullable=True)
    source_language = Column(String(20), nullable=True)
    target_language = Column(String(20), nullable=True)
    segment_count = Column(Integer, default=0)
    word_count = Column(Integer, default=0)
    payload_size = Column(Integer, default=0)
    received_at = Column(DateTime, default=datetime.utcnow)
