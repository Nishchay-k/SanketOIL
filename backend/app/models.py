"""SQLAlchemy ORM models for SANKET's well, evidence, and telemetry records."""

from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geography
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeEngine
from .settings import get_settings


class Base(DeclarativeBase):
    pass


ID_TYPE: TypeEngine = BigInteger().with_variant(Integer, "sqlite")
LOCATION_TYPE: TypeEngine = Geography(geometry_type="POINT", srid=4326, spatial_index=False).with_variant(Text(), "sqlite")
VECTOR_TYPE: TypeEngine = Vector(get_settings().vector_dimensions).with_variant(Text(), "sqlite")


class Well(Base):
    __tablename__ = "wells"
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    well_code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    field: Mapped[str] = mapped_column(String(80), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    location: Mapped[str | None] = mapped_column(LOCATION_TYPE)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    spud_date: Mapped[str | None] = mapped_column(String(32))
    total_depth: Mapped[float] = mapped_column(Float, nullable=False)
    current_depth: Mapped[float | None] = mapped_column(Float)
    formation: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FormationInterval(Base):
    __tablename__ = "formation_intervals"
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    formation: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    top_depth: Mapped[float] = mapped_column(Float, nullable=False)
    bottom_depth: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class Survey(Base):
    __tablename__ = "surveys"
    __table_args__ = (UniqueConstraint("well_id", "measured_depth", name="uq_survey_well_md"),)
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"), nullable=False)
    measured_depth: Mapped[float] = mapped_column(Float, nullable=False)
    tvd: Mapped[float] = mapped_column(Float, nullable=False)
    inclination: Mapped[float] = mapped_column(Float, nullable=False)
    azimuth: Mapped[float] = mapped_column(Float, nullable=False)


class DrillingEvent(Base):
    __tablename__ = "drilling_events"
    __table_args__ = (CheckConstraint("depth_end >= depth_start", name="ck_event_depth_range"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"), nullable=False)
    depth_start: Mapped[float] = mapped_column(Float, nullable=False)
    depth_end: Mapped[float] = mapped_column(Float, nullable=False)
    formation: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    cause: Mapped[str] = mapped_column(Text, nullable=False)
    mitigation: Mapped[str] = mapped_column(Text, nullable=False)
    source_document: Mapped[str] = mapped_column(Text, nullable=False)
    source_page: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DrillingParameter(Base):
    __tablename__ = "drilling_parameters"
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    depth: Mapped[float] = mapped_column(Float, nullable=False)
    rop: Mapped[float] = mapped_column(Float, nullable=False)
    wob: Mapped[float] = mapped_column(Float, nullable=False)
    rpm: Mapped[float] = mapped_column(Float, nullable=False)
    torque: Mapped[float] = mapped_column(Float, nullable=False)
    standpipe_pressure: Mapped[float] = mapped_column(Float, nullable=False)
    mud_weight: Mapped[float] = mapped_column(Float, nullable=False)
    flow_rate: Mapped[float] = mapped_column(Float, nullable=False)
    pit_volume: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="development", server_default="development")


class RiskPrediction(Base):
    __tablename__ = "risk_predictions"
    __table_args__ = (CheckConstraint("risk_score BETWEEN 0 AND 1", name="ck_prediction_score"), CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_prediction_confidence"))
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id"), nullable=False)
    depth: Mapped[float] = mapped_column(Float, nullable=False)
    formation: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_type: Mapped[str] = mapped_column(String(48), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_review: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PredictionEvidence(Base):
    __tablename__ = "prediction_evidence"
    __table_args__ = (UniqueConstraint("prediction_id", "event_id", name="uq_prediction_event"),)
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    prediction_id: Mapped[str] = mapped_column(ForeignKey("risk_predictions.id", ondelete="CASCADE"), nullable=False)
    event_id: Mapped[str] = mapped_column(ForeignKey("drilling_events.id"), nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    original_name: Mapped[str] = mapped_column(String(180), nullable=False)
    stored_name: Mapped[str] = mapped_column(Text, nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(24), nullable=False, default="local", server_default="local")
    media_type: Mapped[str] = mapped_column(String(160), nullable=False)
    extension: Mapped[str] = mapped_column(String(16), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(24), nullable=False)
    extraction_note: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    entities_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    well_id: Mapped[int | None] = mapped_column(ForeignKey("wells.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk"),)
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_page: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR_TYPE)


class ExtractedEntity(Base):
    __tablename__ = "extracted_entities"
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    source_page: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")


class ExtractedEvent(Base):
    __tablename__ = "extracted_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    well_id: Mapped[int | None] = mapped_column(ForeignKey("wells.id", ondelete="SET NULL"))
    well_code: Mapped[str] = mapped_column(String(24), nullable=False, default="", server_default="")
    depth_start: Mapped[float | None] = mapped_column(Float)
    depth_end: Mapped[float | None] = mapped_column(Float)
    formation: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default="")
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    cause: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    mitigation: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    source_page: Mapped[int | None] = mapped_column(Integer)
    extraction_method: Mapped[str] = mapped_column(String(48), nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING", server_default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReservoirProperty(Base):
    __tablename__ = "reservoir_properties"
    __table_args__ = (UniqueConstraint("well_id", "formation", "depth_start", "depth_end", name="uq_reservoir_interval"),)
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"), nullable=False)
    formation: Mapped[str] = mapped_column(String(32), nullable=False)
    depth_start: Mapped[float] = mapped_column(Float, nullable=False)
    depth_end: Mapped[float] = mapped_column(Float, nullable=False)
    lithology: Mapped[str] = mapped_column(Text, nullable=False)
    porosity_percent: Mapped[float | None] = mapped_column(Float)
    permeability_md: Mapped[float | None] = mapped_column(Float)
    pressure_context: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    source_document: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    source_page: Mapped[int | None] = mapped_column(Integer)


class MudProgram(Base):
    __tablename__ = "mud_programs"
    __table_args__ = (UniqueConstraint("well_id", "formation", "depth_start", "depth_end", name="uq_mud_interval"),)
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"), nullable=False)
    formation: Mapped[str] = mapped_column(String(32), nullable=False)
    depth_start: Mapped[float] = mapped_column(Float, nullable=False)
    depth_end: Mapped[float] = mapped_column(Float, nullable=False)
    fluid_type: Mapped[str] = mapped_column(Text, nullable=False)
    mud_weight_min: Mapped[float | None] = mapped_column(Float)
    mud_weight_max: Mapped[float | None] = mapped_column(Float)
    source_document: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    source_page: Mapped[int | None] = mapped_column(Integer)


class CasingProgram(Base):
    __tablename__ = "casing_programs"
    __table_args__ = (UniqueConstraint("well_id", "casing_size", "setting_depth", name="uq_casing_setting"),)
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"), nullable=False)
    casing_size: Mapped[str] = mapped_column(String(48), nullable=False)
    setting_depth: Mapped[float] = mapped_column(Float, nullable=False)
    casing_type: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    source_document: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    source_page: Mapped[int | None] = mapped_column(Integer)


class CementingRecord(Base):
    __tablename__ = "cementing_records"
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"), nullable=False)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("drilling_events.id", ondelete="SET NULL"), unique=True)
    formation: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default="")
    depth_start: Mapped[float | None] = mapped_column(Float)
    depth_end: Mapped[float | None] = mapped_column(Float)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    mitigation: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    source_document: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    source_page: Mapped[int | None] = mapped_column(Integer)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    model_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    training_dataset_version: Mapped[str] = mapped_column(String(80), nullable=False)
    feature_names_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (CheckConstraint("status IN ('NEW','ACKNOWLEDGED','RESOLVED')", name="ck_alert_status"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id", ondelete="CASCADE"), nullable=False)
    prediction_id: Mapped[str | None] = mapped_column(ForeignKey("risk_predictions.id", ondelete="SET NULL"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    risk_type: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    trigger_reason: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_evidence: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="NEW", server_default="NEW")
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("idx_wells_location", Well.location, postgresql_using="gist")
Index("idx_events_well_depth", DrillingEvent.well_id, DrillingEvent.depth_start, DrillingEvent.depth_end)
Index("idx_events_type", DrillingEvent.event_type)
Index("idx_surveys_well_depth", Survey.well_id, Survey.measured_depth)
Index("idx_parameters_well_time", DrillingParameter.well_id, DrillingParameter.timestamp.desc())
Index("idx_alerts_well_status", Alert.well_id, Alert.status, Alert.timestamp)
