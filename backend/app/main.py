"""FastAPI application for the SANKET Nearby Wells Intelligence System."""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import re
import secrets
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import alerts, auth, correlation, documents, embedding_service, intelligence, nlp_extractor, storage, store, telemetry_source
from .settings import ROOT, get_settings

logger = logging.getLogger("sanket.api")
MAX_UPLOAD = get_settings().upload_max_bytes
FRONTEND_DIST = ROOT / "frontend" / "dist"


class WellInput(BaseModel):
    well_code: str = Field(min_length=2, max_length=24, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]+$")
    name: str = Field(min_length=1, max_length=120)
    field: str = Field(min_length=1, max_length=80)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    total_depth: float = Field(gt=0, le=8000)
    formation: str = Field(min_length=1, max_length=32)
    current_depth: float | None = Field(default=None, ge=0, le=8000)
    status: str = "planned"
    spud_date: str | None = None

    @model_validator(mode="after")
    def depth_within_total(self):
        if self.current_depth is not None and self.current_depth > self.total_depth:
            raise ValueError("current_depth cannot exceed total_depth.")
        return self


class RiskInput(BaseModel):
    well_id: str = Field(min_length=1, max_length=24)
    depth: float | None = Field(default=None, ge=0, le=8000)
    formation: str | None = None
    radius_km: float = Field(default=25, ge=1, le=100)


class TelemetryInput(BaseModel):
    well_id: str = "A-101"
    depth: float = Field(ge=0, le=8000)
    formation: str | None = None
    rop: float = Field(ge=0, le=250)
    wob: float = Field(ge=0, le=100)
    rpm: float = Field(ge=0, le=500)
    torque: float = Field(ge=0, le=100)
    standpipe_pressure: float = Field(ge=0, le=500)
    mud_weight: float = Field(ge=0.7, le=3.0)
    flow_rate: float = Field(ge=0, le=10)
    pit_volume: float = Field(ge=0, le=1000)


def _float(value: Any, name: str, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=name + " must be a number.")
    if not (number == number and abs(number) != float("inf")):
        raise HTTPException(status_code=422, detail=name + " must be finite.")
    if minimum is not None and number < minimum:
        raise HTTPException(status_code=422, detail=name + " must be at least " + str(minimum) + ".")
    if maximum is not None and number > maximum:
        raise HTTPException(status_code=422, detail=name + " must be at most " + str(maximum) + ".")
    return number


def _event_filters(query: dict[str, str]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for name, column in (("well_id", "w.well_code"), ("formation", "e.formation"), ("event_type", "e.event_type"), ("severity", "e.severity")):
        value = query.get(name, "").strip()
        if value:
            clauses.append(column + " = ?")
            params.append(value.upper() if name in ("event_type", "severity") else value)
    low = query.get("depth_min", "")
    high = query.get("depth_max", "")
    if low:
        clauses.append("e.depth_end >= ?")
        params.append(_float(low, "depth_min", 0, 8000))
    if high:
        clauses.append("e.depth_start <= ?")
        params.append(_float(high, "depth_max", 0, 8000))
    if low and high and _float(low, "depth_min", 0, 8000) > _float(high, "depth_max", 0, 8000):
        raise HTTPException(status_code=422, detail="depth_min must not exceed depth_max.")
    search = query.get("q", "").strip()
    if search:
        clauses.append("(e.description ILIKE ? OR e.source_document ILIKE ? OR w.well_code ILIKE ?)")
        params.extend(["%" + search + "%"] * 3)
    return " AND ".join(clauses), params


def _check_formation(formation: str) -> str:
    normalized = formation.strip().upper()
    if not store.row("SELECT formation FROM formation_intervals WHERE formation=?", (normalized,)):
        raise HTTPException(status_code=422, detail="formation must match a known formation interval.")
    return normalized


def _raise_api_error(_request: Request, error: StarletteHTTPException) -> JSONResponse:
    message = error.detail if isinstance(error.detail, str) else "The request could not be completed."
    return JSONResponse({"error": {"message": message, "status": error.status_code}}, status_code=error.status_code, headers=error.headers)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.validate()
    store.initialize()
    yield


settings = get_settings()
app = FastAPI(
    title="SANKET Nearby Wells Intelligence API",
    version="1.0.0",
    description="Source-linked well history, explainable risk signals, document extraction, and telemetry.",
    docs_url=None if settings.is_production else "/api/docs",
    redoc_url=None if settings.is_production else "/api/redoc",
    openapi_url=None if settings.is_production else "/api/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)
app.add_exception_handler(StarletteHTTPException, _raise_api_error)


@app.get("/healthz", tags=["health"])
@app.get("/api/health", tags=["health"])
def health():
    try:
        counts = store.row(
            "SELECT (SELECT COUNT(*) FROM wells) AS wells,(SELECT COUNT(*) FROM drilling_events) AS events,(SELECT COUNT(*) FROM drilling_parameters) AS readings,(SELECT COUNT(*) FROM documents) AS documents,(SELECT COUNT(*) FROM extracted_events) AS extracted_events,(SELECT COUNT(*) FROM alerts WHERE status='NEW') AS new_alerts"
        )
        return {"status": "ok", "database": "ok", "dataset": os_dataset_label(), **counts}
    except Exception as error:
        logger.exception("Database health check failed")
        raise HTTPException(status_code=503, detail="The database is not ready.") from error


@app.get("/runtime-config", include_in_schema=False)
def runtime_config():
    runtime = get_settings()
    return {
        "apiBaseUrl": "",
        "authMode": runtime.auth_mode,
        "supabaseUrl": runtime.supabase_url,
        "supabaseAnonKey": runtime.supabase_anon_key,
    }


def os_dataset_label() -> str:
    return get_settings().dataset_label


@app.get("/api/bootstrap", dependencies=[Depends(auth.require_user)])
def bootstrap():
    return store.get_bootstrap_data()


@app.get("/api/operations/context", dependencies=[Depends(auth.require_user)])
def operations_context(
    well_id: str = "A-101",
    radius_km: float = Query(default=25, ge=1, le=100),
    depth: float | None = Query(default=None, ge=0, le=8000),
    formation: str | None = None,
):
    """Load the dashboard's well context in one serverless request."""
    active = store.get_well(well_id)
    if not active:
        raise HTTPException(status_code=404, detail="Well " + well_id + " was not found.")
    depth_value = active["current_depth"] or 0 if depth is None else depth
    formation_value = _check_formation(formation or active["formation"])
    event_rows = store.get_events()
    nearby = intelligence.rank_offsets(active, radius_km, depth_value, formation_value, event_rows)
    prediction_response = predict_risk(RiskInput(
        well_id=well_id,
        depth=depth_value,
        formation=formation_value,
        radius_km=radius_km,
    ))
    readings = store.get_parameters(active["id"], 60)
    correlation_result = correlation.build(well_id, depth_value, formation_value, radius_km, nearby, event_rows)
    generated_alerts = prediction_response["prediction"].get("alerts", [])
    return {
        "nearby": {"well_id": well_id, "radius_km": radius_km, "depth": depth_value, "formation": formation_value, "wells": nearby, "count": len(nearby)},
        "events": {"events": event_rows, "count": len(event_rows)},
        "telemetry": {"well_code": well_id, "readings": readings},
        "risk": prediction_response,
        "correlation": {"correlation": correlation_result},
        "alerts": {"alerts": generated_alerts, "count": len(generated_alerts)},
    }


@app.get("/api/formations", dependencies=[Depends(auth.require_user)])
def formations():
    result = store.rows("SELECT formation AS name,top_depth,bottom_depth,description FROM formation_intervals ORDER BY top_depth")
    return {"formations": result, "count": len(result)}


@app.get("/api/wells", dependencies=[Depends(auth.require_user)])
def wells(field: str = "", status: str = "", q: str = ""):
    result = store.get_wells()
    if field.strip():
        result = [item for item in result if item["field"].lower() == field.strip().lower()]
    if status.strip():
        result = [item for item in result if item["status"].lower() == status.strip().lower()]
    if q.strip():
        search = q.strip().lower()
        result = [item for item in result if search in item["well_code"].lower() or search in item["field"].lower() or search in item["name"].lower()]
    return {"wells": result, "count": len(result), "dataset": os_dataset_label()}


@app.post("/api/wells", status_code=201, dependencies=[Depends(auth.require_user)])
def create_well(payload: WellInput):
    values = payload.model_dump()
    values["well_code"] = values["well_code"].strip().upper()
    values["field"] = values["field"].strip()
    values["name"] = values["name"].strip()
    values["formation"] = _check_formation(values["formation"])
    if values["status"] not in {"planned", "drilling", "paused", "completed"}:
        raise HTTPException(status_code=422, detail="Status must be planned, drilling, paused, or completed.")
    try:
        values["id"] = store.add_well(values)
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="A well with code " + values["well_code"] + " already exists.") from error
    return {"well": values}


@app.get("/api/wells/nearby", dependencies=[Depends(auth.require_user)])
def nearby_wells(well_id: str = "A-101", radius_km: float = Query(default=10, ge=1, le=100), depth: float | None = Query(default=None, ge=0, le=8000), formation: str | None = None):
    active = store.get_well(well_id)
    if not active:
        raise HTTPException(status_code=404, detail="Well " + well_id + " was not found.")
    depth_value = active["current_depth"] or 0 if depth is None else depth
    formation_value = formation or active["formation"]
    ranked = intelligence.rank_offsets(active, radius_km, depth_value, formation_value)
    return {"well_id": well_id, "radius_km": radius_km, "depth": depth_value, "formation": formation_value, "wells": ranked, "count": len(ranked)}


@app.get("/api/wells/{well_code}/events", dependencies=[Depends(auth.require_user)])
def well_events(well_code: str, request: Request):
    if not store.get_well(well_code):
        raise HTTPException(status_code=404, detail="Well " + well_code + " was not found.")
    where, params = _event_filters(dict(request.query_params))
    clauses = ["w.well_code = ?"]
    all_params: list[Any] = [well_code]
    if where:
        clauses.append(where)
        all_params.extend(params)
    result = store.get_events(" AND ".join(clauses), all_params)
    return {"well_code": well_code, "events": result, "count": len(result)}


@app.get("/api/wells/{well_code}", dependencies=[Depends(auth.require_user)])
def well_detail(well_code: str):
    active = store.get_well(well_code)
    if not active:
        raise HTTPException(status_code=404, detail="Well " + well_code + " was not found.")
    detail = {
        **active,
        "surveys": store.get_surveys(active["id"]),
        "events": store.get_events("w.well_code = ?", (well_code,)),
        "parameters": store.get_parameters(active["id"], 12),
        **store.get_well_context(active["id"]),
    }
    return {"well": detail}


@app.get("/api/events", dependencies=[Depends(auth.require_user)])
def events(request: Request):
    where, params = _event_filters(dict(request.query_params))
    result = store.get_events(where, params)
    return {"events": result, "count": len(result)}


@app.get("/api/events/{event_id}", dependencies=[Depends(auth.require_user)])
def event_detail(event_id: str):
    event = store.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event " + event_id + " was not found.")
    return {"event": event}


@app.get("/api/search", dependencies=[Depends(auth.require_user)])
def search(q: str = "", limit: int = Query(default=20, ge=1, le=30)):
    return intelligence.search_evidence(q, limit)


@app.get("/api/correlation", dependencies=[Depends(auth.require_user)])
def correlation_view(well_id: str = "A-101", depth: float | None = Query(default=None, ge=0, le=8000), formation: str | None = None, radius_km: float = Query(default=10, ge=1, le=100)):
    active = store.get_well(well_id)
    if not active:
        raise HTTPException(status_code=404, detail="Well " + well_id + " was not found.")
    depth_value = active["current_depth"] or 0 if depth is None else depth
    formation_value = _check_formation(formation or active["formation"])
    return {"correlation": correlation.build(well_id, depth_value, formation_value, radius_km)}


@app.get("/api/alerts", dependencies=[Depends(auth.require_user)])
def alerts_list(well_id: str | None = None, status: str | None = None):
    normalized = status.strip().upper() if status else None
    if normalized and normalized not in {"NEW", "ACKNOWLEDGED", "RESOLVED"}:
        raise HTTPException(status_code=422, detail="status must be NEW, ACKNOWLEDGED, or RESOLVED.")
    result = alerts.list_alerts(well_id.strip() if well_id else None, normalized)
    return {"alerts": result, "count": len(result)}


@app.post("/api/alerts/{alert_id}/{action}", dependencies=[Depends(auth.require_user)])
def update_alert(alert_id: str, action: str):
    status = {"acknowledge": "ACKNOWLEDGED", "resolve": "RESOLVED"}.get(action)
    if not status:
        raise HTTPException(status_code=404, detail="Alert action not found.")
    updated = alerts.update_status(alert_id, status)
    if not updated:
        raise HTTPException(status_code=404, detail="Alert " + alert_id + " was not found.")
    return {"alert": updated}


@app.get("/api/models", dependencies=[Depends(auth.require_user)])
def model_versions():
    result = store.get_model_versions()
    for item in result:
        try:
            item["feature_names"] = json.loads(item.pop("feature_names_json") or "[]")
            item["metrics"] = json.loads(item.pop("metrics_json") or "{}")
        except json.JSONDecodeError:
            item["feature_names"], item["metrics"] = [], {}
    return {"models": result, "count": len(result)}


@app.get("/api/documents", dependencies=[Depends(auth.require_user)])
def documents_list():
    return {
        "documents": store.get_documents(),
        "supported_extensions": sorted(documents.SUPPORTED_EXTENSIONS),
        "max_upload_bytes": MAX_UPLOAD,
        "capabilities": {
            **documents.capabilities(),
            "storage_backend": get_settings().storage_backend,
            "pgvector_search": store.vector_search_available(),
            "embedding_model_configured": embedding_service.available(),
        },
    }


@app.get("/api/documents/{document_id}/extractions", dependencies=[Depends(auth.require_user)])
def document_extractions(document_id: str):
    if not store.get_document(document_id):
        raise HTTPException(status_code=404, detail="Document " + document_id + " was not found.")
    return {"document_id": document_id, **store.get_document_extractions(document_id)}


@app.get("/api/documents/{document_id}/download", dependencies=[Depends(auth.require_user)])
def document_download(document_id: str):
    document = store.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document " + document_id + " was not found.")
    try:
        result = storage.signed_download_url(document["storage_backend"], document["stored_name"])
        if result.startswith("local:"):
            return FileResponse(storage.local_file_path(document["stored_name"]), media_type=document["media_type"], filename=document["original_name"])
        return {"url": result, "expires_in": 300}
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/api/documents/{document_id}", dependencies=[Depends(auth.require_user)])
def document_detail(document_id: str):
    document = store.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document " + document_id + " was not found.")
    try:
        document["entities"] = json.loads(document.pop("entities_json") or "{}")
    except json.JSONDecodeError:
        document["entities"] = {}
    document.pop("stored_name", None)
    document.pop("storage_backend", None)
    document["extractions"] = store.get_document_extractions(document_id)
    return {"document": document}


@app.post("/api/documents", status_code=201, dependencies=[Depends(auth.require_user)])
def upload_document(file: UploadFile = File(...)):
    original_name = Path((file.filename or "").replace("\\", "/")).name
    if not original_name:
        raise HTTPException(status_code=400, detail="Choose a non-empty document in the file field.")
    safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", original_name).strip(" .")[:140]
    extension = Path(safe_name).suffix.lower()
    if extension not in documents.SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Supported formats: PDF, DOCX, TXT, MD, CSV, JSON, LOG, PNG, JPG, JPEG, TIF, and TIFF.")
    upload_data = file.file.read(MAX_UPLOAD + 1)
    if not upload_data:
        raise HTTPException(status_code=400, detail="Choose a non-empty document in the file field.")
    if len(upload_data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="Document uploads are limited to " + str(MAX_UPLOAD // (1024 * 1024)) + " MB.")
    content_type = file.content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    document_id = "DOC-" + uuid.uuid4().hex[:12].upper()
    storage_key = document_id + "/" + (safe_name or ("document" + extension))
    temp_path = None
    stored_backend = None
    try:
        with tempfile.NamedTemporaryFile(prefix="sanket-upload-", suffix=extension, delete=False) as temp_file:
            temp_file.write(upload_data)
            temp_path = Path(temp_file.name)
        pages, extraction_note = documents.extract_pages(temp_path, extension)
        extracted_text = "\n\n".join(text for _, text in pages)[:documents.MAX_EXTRACTED_CHARS]
        extraction_status = "ready" if extracted_text.strip() else "needs_ocr" if extension in {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"} else "no_text"
        known_wells = [item["well_code"] for item in store.get_wells()]
        knowledge = nlp_extractor.extract_document(pages, known_wells)
        extracted_entities = knowledge["entities"]
        extracted_events = knowledge["events"]
        entity_index: dict[str, list[str]] = {}
        for entity in extracted_entities:
            entity_index.setdefault(entity["entity_type"], [])
            value = entity["normalized_value"] or entity["entity_value"]
            if value not in entity_index[entity["entity_type"]]:
                entity_index[entity["entity_type"]].append(value)
        linked_codes = set()
        for event in extracted_events:
            event_well = store.get_well(event["well_code"]) if event.get("well_code") else None
            event["well_id"] = event_well["id"] if event_well else None
            if event_well:
                linked_codes.add(event_well["well_code"])
        for code in entity_index.get("well", []):
            if store.get_well(code):
                linked_codes.add(code)
        linked_well = store.get_well(next(iter(linked_codes))) if len(linked_codes) == 1 else None
        stored_backend, stored_name = storage.save_document(storage_key, upload_data, content_type)
        record = {
            "id": document_id,
            "original_name": safe_name or ("document" + extension),
            "stored_name": stored_name,
            "storage_backend": stored_backend,
            "media_type": content_type,
            "extension": extension,
            "size_bytes": len(upload_data),
            "extraction_status": extraction_status,
            "extraction_note": extraction_note,
            "extracted_text": extracted_text,
            "entities_json": json.dumps(entity_index, ensure_ascii=False, separators=(",", ":")),
            "well_id": linked_well["id"] if linked_well else None,
        }
        chunks = documents.make_page_chunks(pages)
        vectors = embedding_service.encode_texts([content for _, content in chunks]) if chunks else None
        store.add_document(record, chunks, extracted_entities, extracted_events, embeddings=vectors)
        for key in ("stored_name", "storage_backend", "entities_json", "extracted_text"):
            record.pop(key, None)
        record["extracted_chars"] = len(extracted_text)
        record["entities"] = entity_index
        record["entity_count"] = len(extracted_entities)
        record["extracted_event_count"] = len(extracted_events)
        record["well_code"] = linked_well["well_code"] if linked_well else None
        return {"document": record}
    except HTTPException:
        if stored_backend:
            storage.delete_document(stored_backend, storage_key)
        raise
    except Exception as error:
        if stored_backend:
            storage.delete_document(stored_backend, storage_key)
        logger.exception("Document extraction or storage failed")
        raise HTTPException(status_code=422, detail="This file could not be processed. Check the file and configured extraction/storage services.") from error
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        file.file.close()


@app.post("/api/risk/predict", dependencies=[Depends(auth.require_user)])
def predict_risk(payload: RiskInput):
    well_code = payload.well_id.strip()
    active = store.get_well(well_code)
    if not active:
        raise HTTPException(status_code=404, detail="Well " + well_code + " was not found.")
    depth = active["current_depth"] or 0 if payload.depth is None else payload.depth
    formation = _check_formation(payload.formation or active["formation"])
    radius = payload.radius_km
    result = intelligence.calculate_risk(well_code, depth, formation, radius)
    result["radius_km"] = radius
    prediction_id = "RP-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(3).upper()
    result["prediction_id"] = prediction_id
    result["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    store.save_prediction({
        "id": prediction_id,
        "well_id": active["id"],
        "depth": depth,
        "formation": formation,
        "risk_type": result["risk_type"],
        "risk_score": result["risk_score"],
        "confidence": result["confidence"],
        "severity": result["severity"],
        "explanation": result["explanation"],
        "recommended_review": result["recommended_review"],
        "model_version": result["model_version"],
        "created_at": result["created_at"],
    }, result["evidence"])
    result["alerts"] = alerts.evaluate(well_code, result, prediction_id, result["created_at"])
    return {"prediction": result}


@app.get("/api/risk/{prediction_id}", dependencies=[Depends(auth.require_user)])
def risk_prediction(prediction_id: str):
    prediction = store.get_prediction(prediction_id)
    if not prediction:
        raise HTTPException(status_code=404, detail="Risk prediction " + prediction_id + " was not found.")
    return {"prediction": prediction}


@app.get("/api/telemetry", dependencies=[Depends(auth.require_user)])
def telemetry(well_id: str = "A-101"):
    active = store.get_well(well_id)
    if not active:
        raise HTTPException(status_code=404, detail="Well " + well_id + " was not found.")
    return {"well_code": well_id, "readings": store.get_parameters(active["id"], 60)}


@app.post("/api/telemetry", dependencies=[Depends(auth.require_user)])
def ingest_telemetry(payload: TelemetryInput):
    well_code = payload.well_id.strip()
    active = store.get_well(well_code)
    if not active:
        raise HTTPException(status_code=404, detail="Well " + well_code + " was not found.")
    values = payload.model_dump(exclude={"well_id", "formation"})
    formation = _check_formation(payload.formation or active["formation"])
    values["formation"] = formation
    values = telemetry_source.ACTIVE_TELEMETRY_SOURCE.normalize(values)
    reading = store.add_telemetry(well_code, values)
    risk = intelligence.calculate_risk(well_code, values["depth"], formation, 10)
    generated_alerts = alerts.evaluate(well_code, risk, timestamp=values["timestamp"]) if risk else []
    return {"reading": reading, "dataset": os_dataset_label(), "alerts": generated_alerts}


async def _telemetry_stream(well_code: str):
    active = store.get_well(well_code)
    if not active:
        raise HTTPException(status_code=404, detail="Well " + well_code + " was not found.")
    yield "retry: 3000\n\n"
    last_timestamp = None
    deadline = time.monotonic() + 35
    try:
        while time.monotonic() < deadline:
            readings = store.get_parameters(active["id"], 1)
            latest = readings[0] if readings else None
            timestamp = latest["timestamp"] if latest else None
            if latest and timestamp != last_timestamp:
                packet = json.dumps({"well_code": well_code, "reading": latest}, separators=(",", ":"))
                yield "event: telemetry\ndata: " + packet + "\n\n"
                for alert in alerts.list_alerts(well_code, "NEW"):
                    yield "event: alert\ndata: " + json.dumps(alert, ensure_ascii=False, separators=(",", ":")) + "\n\n"
                last_timestamp = timestamp
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(max(0.25, get_settings().stream_poll_seconds))
    except asyncio.CancelledError:
        return


@app.get("/api/telemetry/stream", dependencies=[Depends(auth.require_user)])
def telemetry_stream(well_id: str = "A-101"):
    if not store.get_well(well_id):
        raise HTTPException(status_code=404, detail="Well " + well_id + " was not found.")
    return StreamingResponse(
        _telemetry_stream(well_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.get("/", include_in_schema=False)
def frontend_root():
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {"service": "SANKET API", "status": "ok", "frontend": "Run `npm run dev --prefix frontend` for the Vite development server."}


if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")


def main() -> None:
    import uvicorn

    runtime = get_settings()
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=runtime.port, proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
