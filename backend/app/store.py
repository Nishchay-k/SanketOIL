"""SQLAlchemy-backed persistence with PostgreSQL as the deployment database."""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from threading import Lock
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from . import models
from .models import Well
from .sample_data import CASING_PROGRAM_SPECS, MUD_PROGRAM_SPECS, RESERVOIR_SPECS, build_development_data
from .settings import get_settings, sqlalchemy_database_url

_engine: Engine | None = None
_engine_lock = Lock()
_database_url: str | None = None


class Record(dict):
    """Mapping row that keeps sqlite.Row's integer-index behavior for callers."""

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class ResultAdapter:
    def __init__(self, result: Any):
        self._result = result
        self.rowcount = result.rowcount

    @staticmethod
    def _record(row: Any) -> Record | None:
        if row is None:
            return None
        values = dict(row._mapping)
        # Geography objects are internal spatial state, never API response data.
        values.pop("location", None)
        for key, value in tuple(values.items()):
            if isinstance(value, datetime):
                values[key] = value.isoformat(timespec="seconds").replace("+00:00", "Z")
            elif isinstance(value, Decimal):
                values[key] = float(value)
        return Record(values)

    def fetchone(self) -> Record | None:
        return self._record(self._result.fetchone())

    def fetchall(self) -> list[Record]:
        return [self._record(row) for row in self._result.fetchall()]

    def __iter__(self):
        for row in self._result:
            yield self._record(row)

    @property
    def lastrowid(self):
        return getattr(self._result, "lastrowid", None)


def _params(sql: str, values: Any) -> tuple[Any, Any]:
    if values is None:
        return text(sql), {}
    if isinstance(values, dict):
        return text(sql), values
    if isinstance(values, list) and values and isinstance(values[0], dict):
        return text(sql), values
    values = tuple(values)
    if not values:
        return text(sql), {}
    index = 0

    def replace(_match):
        nonlocal index
        placeholder = f":p{index}"
        index += 1
        return placeholder

    statement = re.sub(r"\?", replace, sql)
    if values and isinstance(values[0], (tuple, list)):
        batch = []
        for row in values:
            if len(row) != index:
                raise ValueError("All SQL batch rows must provide the same number of values.")
            batch.append({f"p{position}": value for position, value in enumerate(row)})
        return text(statement), batch
    if len(values) != index:
        raise ValueError(f"SQL expected {index} positional values but received {len(values)}.")
    return text(statement), {f"p{position}": value for position, value in enumerate(values)}


class ConnectionAdapter:
    def __init__(self, connection: Connection):
        self._connection = connection

    def execute(self, sql: str, params: Any = ()) -> ResultAdapter:
        statement, bindings = _params(sql, params)
        return ResultAdapter(self._connection.execute(statement, bindings))

    def executemany(self, sql: str, params: Any) -> ResultAdapter:
        if not params:
            return ResultAdapter(self._connection.execute(text("SELECT 1 WHERE 1=0")))
        statement, bindings = _params(sql, params)
        return ResultAdapter(self._connection.execute(statement, bindings))


def configure_database(database_url: str | None = None) -> None:
    """Replace the engine. Primarily useful for isolated tests and migration tools."""
    global _engine, _database_url
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _database_url = database_url


def engine() -> Engine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                url = sqlalchemy_database_url(_database_url or get_settings().database_url)
                kwargs: dict[str, Any] = {"pool_pre_ping": True, "future": True}
                if url.startswith("sqlite"):
                    kwargs["connect_args"] = {"check_same_thread": False}
                elif url.startswith("postgresql+psycopg://") and get_settings().is_production:
                    # Vercel functions are short-lived and Supabase's transaction pooler
                    # cannot retain prepared statements between backend connections.
                    kwargs.update({"pool_size": 1, "max_overflow": 0})
                    kwargs["connect_args"] = {"prepare_threshold": None}
                _engine = create_engine(url, **kwargs)
    return _engine


def is_postgres() -> bool:
    return engine().dialect.name == "postgresql"


@contextmanager
def connection_scope():
    with engine().begin() as connection:
        yield ConnectionAdapter(connection)


def _dt(value: Any) -> Any:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def _seed(connection: ConnectionAdapter) -> None:
    data = build_development_data()
    connection.executemany(
        """INSERT INTO wells(well_code,name,field,latitude,longitude,status,spud_date,total_depth,current_depth,formation)
           VALUES(:well_code,:name,:field,:latitude,:longitude,:status,:spud_date,:total_depth,:current_depth,:formation)""",
        data["wells"],
    )
    connection.executemany(
        "INSERT INTO formation_intervals(formation,top_depth,bottom_depth,description) VALUES(:name,:top_depth,:bottom_depth,:description)",
        data["formations"],
    )
    well_ids = {row["well_code"]: row["id"] for row in connection.execute("SELECT id,well_code FROM wells")}
    for survey in data["surveys"]:
        survey["well_id"] = well_ids[survey.pop("well_code")]
    connection.executemany(
        "INSERT INTO surveys(well_id,measured_depth,tvd,inclination,azimuth) VALUES(:well_id,:measured_depth,:tvd,:inclination,:azimuth)",
        data["surveys"],
    )
    for event in data["events"]:
        event["well_id"] = well_ids[event.pop("well_code")]
    connection.executemany(
        """INSERT INTO drilling_events(id,well_id,depth_start,depth_end,formation,event_type,severity,description,cause,mitigation,source_document,source_page)
           VALUES(:event_id,:well_id,:depth_start,:depth_end,:formation,:event_type,:severity,:description,:cause,:mitigation,:source_document,:source_page)""",
        data["events"],
    )
    parameter_rows = []
    for item in data["parameters"]:
        values = dict(item, well_id=well_ids[item["well_code"]])
        values.pop("well_code", None)
        values["timestamp"] = _dt(values["timestamp"])
        parameter_rows.append(values)
    connection.executemany(
        """INSERT INTO drilling_parameters(well_id,timestamp,depth,rop,wob,rpm,torque,standpipe_pressure,mud_weight,flow_rate,pit_volume)
           VALUES(:well_id,:timestamp,:depth,:rop,:wob,:rpm,:torque,:standpipe_pressure,:mud_weight,:flow_rate,:pit_volume)""",
        parameter_rows,
    )
    if is_postgres():
        connection.execute("UPDATE wells SET location=ST_SetSRID(ST_MakePoint(longitude,latitude),4326)::geography")


def _seed_context(connection: ConnectionAdapter) -> None:
    well_ids = {item["well_code"]: item["id"] for item in connection.execute("SELECT id,well_code FROM wells")}
    for code, formation, top, bottom, lithology, porosity, permeability, pressure_context in RESERVOIR_SPECS:
        if code in well_ids:
            connection.execute(
                """INSERT INTO reservoir_properties
                   (well_id,formation,depth_start,depth_end,lithology,porosity_percent,permeability_md,pressure_context,source_document,source_page)
                   VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT (well_id,formation,depth_start,depth_end) DO NOTHING""",
                (well_ids[code], formation, top, bottom, lithology, porosity, permeability, pressure_context, "DEV-GEO-" + code + "-26", 1),
            )
    for code, formation, top, bottom, fluid, minimum, maximum in MUD_PROGRAM_SPECS:
        if code in well_ids:
            connection.execute(
                """INSERT INTO mud_programs
                   (well_id,formation,depth_start,depth_end,fluid_type,mud_weight_min,mud_weight_max,source_document,source_page)
                   VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT (well_id,formation,depth_start,depth_end) DO NOTHING""",
                (well_ids[code], formation, top, bottom, fluid, minimum, maximum, "DEV-MUD-" + code + "-26", 1),
            )
    for code, size, depth, casing_type in CASING_PROGRAM_SPECS:
        if code in well_ids:
            connection.execute(
                """INSERT INTO casing_programs
                   (well_id,casing_size,setting_depth,casing_type,source_document,source_page)
                   VALUES(?,?,?,?,?,?) ON CONFLICT (well_id,casing_size,setting_depth) DO NOTHING""",
                (well_ids[code], size, depth, casing_type, "DEV-CASING-" + code + "-26", 1),
            )
    connection.execute(
        """INSERT INTO cementing_records
           (well_id,event_id,formation,depth_start,depth_end,summary,mitigation,source_document,source_page)
           SELECT well_id,id,formation,depth_start,depth_end,description,mitigation,source_document,source_page
           FROM drilling_events WHERE event_type='CEMENTING' ON CONFLICT (event_id) DO NOTHING"""
    )
    for version in (
        ("rules-offset-v1.1", "explainable-rules", "active-fallback", "synthetic-development-v1", "[]", "{}", "", "No verified training labels are available; rules and offset evidence remain active."),
        ("pressure-offset-v1.0", "formation-pressure-indicator", "development-estimator", "synthetic-development-v1", '["formation","depth","offset_pressure_events","mud_weight"]', "{}", "", "Evidence-linked development indicator only; no measured PPFG curve."),
    ):
        connection.execute(
            """INSERT INTO model_versions(model_version,model_type,status,training_dataset_version,feature_names_json,metrics_json,artifact_path,note)
               VALUES(?,?,?,?,?,?,?,?) ON CONFLICT (model_version) DO NOTHING""",
            version,
        )


def initialize() -> None:
    settings = get_settings()
    target = engine()
    if settings.auto_create_schema:
        if target.dialect.name == "postgresql":
            with target.begin() as connection:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        models.Base.metadata.create_all(target)
    with connection_scope() as connection:
        connection.execute("SELECT 1")
        count = connection.execute("SELECT COUNT(*) AS count FROM wells").fetchone()["count"]
        if settings.seed_demo_data and count == 0:
            _seed(connection)
        if settings.seed_demo_data:
            _seed_context(connection)


def rows(sql: str, params: Any = ()) -> list[Record]:
    with connection_scope() as connection:
        return connection.execute(sql, params).fetchall()


def row(sql: str, params: Any = ()) -> Record | None:
    with connection_scope() as connection:
        return connection.execute(sql, params).fetchone()


def insert(sql: str, params: Any = ()) -> int | None:
    with connection_scope() as connection:
        return connection.execute(sql, params).lastrowid


def get_wells() -> list[Record]:
    return rows("SELECT id,well_code,name,field,latitude,longitude,status,spud_date,total_depth,current_depth,formation,created_at FROM wells ORDER BY field,well_code")


def get_bootstrap_data() -> dict[str, Any]:
    """Fetch the records needed for the initial application render."""
    with connection_scope() as connection:
        wells = connection.execute("SELECT id,well_code,name,field,latitude,longitude,status,spud_date,total_depth,current_depth,formation,created_at FROM wells ORDER BY field,well_code").fetchall()
        formations = connection.execute("SELECT formation AS name,top_depth,bottom_depth,description FROM formation_intervals ORDER BY top_depth").fetchall()
        counts = connection.execute(
            "SELECT (SELECT COUNT(*) FROM wells) AS wells,(SELECT COUNT(*) FROM drilling_events) AS events,(SELECT COUNT(*) FROM drilling_parameters) AS readings,(SELECT COUNT(*) FROM documents) AS documents,(SELECT COUNT(*) FROM extracted_events) AS extracted_events,(SELECT COUNT(*) FROM alerts WHERE status='NEW') AS new_alerts"
        ).fetchone()
    return {"wells": wells, "formations": formations, "health": {"status": "ok", "dataset": "development", **counts}}


def add_well(values: dict[str, Any]) -> int:
    with Session(engine()) as session, session.begin():
        well = Well(**{key: values.get(key) for key in ("well_code", "name", "field", "latitude", "longitude", "status", "spud_date", "total_depth", "current_depth", "formation")})
        session.add(well)
        session.flush()
        if is_postgres():
            session.execute(text("UPDATE wells SET location=ST_SetSRID(ST_MakePoint(:longitude,:latitude),4326)::geography WHERE id=:id"), {"longitude": well.longitude, "latitude": well.latitude, "id": well.id})
        return well.id


def get_well(well_code: str) -> Record | None:
    return row("SELECT id,well_code,name,field,latitude,longitude,status,spud_date,total_depth,current_depth,formation,created_at FROM wells WHERE well_code = ?", (well_code,))


def get_nearby_wells(well_code: str, radius_km: float) -> list[Record] | None:
    """Return PostGIS-filtered nearby offsets, or None for non-PostgreSQL test engines."""
    if not is_postgres():
        return None
    return rows(
        """SELECT w.id,w.well_code,w.name,w.field,w.latitude,w.longitude,w.status,w.spud_date,w.total_depth,w.current_depth,w.formation,w.created_at,
                  ST_Distance(w.location,active.location)/1000.0 AS distance_km
           FROM wells w CROSS JOIN (SELECT location FROM wells WHERE well_code=?) active
           WHERE w.well_code<>? AND ST_DWithin(w.location,active.location,?*1000.0)
           ORDER BY distance_km,w.well_code""",
        (well_code, well_code, radius_km),
    )


def get_well_contexts(well_ids: list[int]) -> dict[int, dict[str, list[Record]]]:
    """Fetch structured context for several wells with one query per record type."""
    unique_ids = list(dict.fromkeys(well_ids))
    result = {
        well_id: {
            "reservoir_properties": [],
            "mud_programs": [],
            "casing_programs": [],
            "cementing_records": [],
        }
        for well_id in unique_ids
    }
    if not unique_ids:
        return result
    placeholders = ",".join("?" for _ in unique_ids)
    queries = {
        "reservoir_properties": f"SELECT * FROM reservoir_properties WHERE well_id IN ({placeholders}) ORDER BY well_id,depth_start",
        "mud_programs": f"SELECT * FROM mud_programs WHERE well_id IN ({placeholders}) ORDER BY well_id,depth_start",
        "casing_programs": f"SELECT * FROM casing_programs WHERE well_id IN ({placeholders}) ORDER BY well_id,setting_depth",
        "cementing_records": f"SELECT * FROM cementing_records WHERE well_id IN ({placeholders}) ORDER BY well_id,depth_start",
    }
    with connection_scope() as connection:
        for key, sql in queries.items():
            for record in connection.execute(sql, unique_ids):
                result[record["well_id"]][key].append(record)
    return result


def get_parameters_for_wells(well_ids: list[int], limit: int = 60) -> dict[int, list[Record]]:
    """Fetch recent readings for multiple wells in one database round trip."""
    unique_ids = list(dict.fromkeys(well_ids))
    result = {well_id: [] for well_id in unique_ids}
    if not unique_ids:
        return result
    placeholders = ",".join("?" for _ in unique_ids)
    sql = f"""SELECT well_id,timestamp,depth,rop,wob,rpm,torque,standpipe_pressure,mud_weight,flow_rate,pit_volume,source
              FROM (
                  SELECT well_id,timestamp,depth,rop,wob,rpm,torque,standpipe_pressure,mud_weight,flow_rate,pit_volume,source,
                         ROW_NUMBER() OVER (PARTITION BY well_id ORDER BY timestamp DESC) AS reading_number
                  FROM drilling_parameters WHERE well_id IN ({placeholders})
              ) recent
              WHERE reading_number<=?
              ORDER BY well_id,timestamp DESC"""
    with connection_scope() as connection:
        for record in connection.execute(sql, (*unique_ids, limit)):
            result[record["well_id"]].append(record)
    return result


def get_surveys_for_wells(well_ids: list[int]) -> dict[int, list[Record]]:
    """Fetch survey stations for multiple wells in one database round trip."""
    unique_ids = list(dict.fromkeys(well_ids))
    result = {well_id: [] for well_id in unique_ids}
    if not unique_ids:
        return result
    placeholders = ",".join("?" for _ in unique_ids)
    sql = f"SELECT well_id,measured_depth,tvd,inclination,azimuth FROM surveys WHERE well_id IN ({placeholders}) ORDER BY well_id,measured_depth"
    with connection_scope() as connection:
        for record in connection.execute(sql, unique_ids):
            result[record["well_id"]].append(record)
    return result


def get_events(where: str = "", params: Any = ()) -> list[Record]:
    sql = """SELECT e.*, w.well_code, w.name AS well_name, w.field, w.latitude, w.longitude
             FROM drilling_events e JOIN wells w ON w.id=e.well_id"""
    if where:
        sql += " WHERE " + where
    sql += " ORDER BY e.depth_start, w.well_code"
    return rows(sql, params)


def get_event(event_id: str) -> Record | None:
    events = get_events("e.id = ?", (event_id,))
    return events[0] if events else None


def get_surveys(well_id: int) -> list[Record]:
    return rows("SELECT measured_depth,tvd,inclination,azimuth FROM surveys WHERE well_id=? ORDER BY measured_depth", (well_id,))


def get_parameters(well_id: int, limit: int = 60) -> list[Record]:
    return rows("SELECT timestamp,depth,rop,wob,rpm,torque,standpipe_pressure,mud_weight,flow_rate,pit_volume,source FROM drilling_parameters WHERE well_id=? ORDER BY timestamp DESC LIMIT ?", (well_id, limit))


def add_telemetry(well_code: str, values: dict[str, Any]) -> Record | None:
    well = get_well(well_code)
    if not well:
        return None
    timestamp = _dt(values.get("timestamp"))
    with connection_scope() as connection:
        connection.execute(
            """INSERT INTO drilling_parameters(well_id,timestamp,depth,rop,wob,rpm,torque,standpipe_pressure,mud_weight,flow_rate,pit_volume,source)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (well["id"], timestamp, values["depth"], values["rop"], values["wob"], values["rpm"], values["torque"], values["standpipe_pressure"], values["mud_weight"], values["flow_rate"], values["pit_volume"], values.get("source", "development")),
        )
        connection.execute("UPDATE wells SET current_depth=?,formation=? WHERE id=?", (values["depth"], values.get("formation", well["formation"]), well["id"]))
    return get_parameters(well["id"], 1)[0]


def save_prediction(prediction: dict[str, Any], evidence: list[dict[str, Any]]) -> None:
    values = dict(prediction, created_at=_dt(prediction["created_at"]))
    with connection_scope() as connection:
        connection.execute("""INSERT INTO risk_predictions(id,well_id,depth,formation,risk_type,risk_score,confidence,severity,explanation,recommended_review,model_version,created_at)
           VALUES(:id,:well_id,:depth,:formation,:risk_type,:risk_score,:confidence,:severity,:explanation,:recommended_review,:model_version,:created_at)""", values)
        connection.executemany("INSERT INTO prediction_evidence(prediction_id,event_id,similarity_score,reason) VALUES(?,?,?,?)", [(prediction["id"], item["event_id"], item["relevance"], item["reason"]) for item in evidence])


def get_prediction(prediction_id: str) -> Record | None:
    prediction = row("SELECT * FROM risk_predictions WHERE id = ?", (prediction_id,))
    if prediction:
        prediction["evidence"] = rows("""SELECT e.id AS event_id,w.well_code,e.depth_start,e.depth_end,e.formation,e.event_type,e.severity,e.source_document,e.source_page,e.mitigation,pe.similarity_score,pe.reason
               FROM prediction_evidence pe JOIN drilling_events e ON e.id=pe.event_id JOIN wells w ON w.id=e.well_id
               WHERE pe.prediction_id=? ORDER BY pe.similarity_score DESC""", (prediction_id,))
    return prediction


def add_document(document: dict[str, Any], chunks: list[Any], entities=(), extracted_events=(), embeddings=None) -> None:
    normalized_chunks = [(item[0], item[1]) if isinstance(item, (tuple, list)) and len(item) == 2 else (None, item) for item in chunks]
    with connection_scope() as connection:
        connection.execute("""INSERT INTO documents(id,original_name,stored_name,storage_backend,media_type,extension,size_bytes,extraction_status,extraction_note,extracted_text,entities_json,well_id)
               VALUES(:id,:original_name,:stored_name,:storage_backend,:media_type,:extension,:size_bytes,:extraction_status,:extraction_note,:extracted_text,:entities_json,:well_id)""",
            dict(document, storage_backend=document.get("storage_backend", "local")))
        embeddings = embeddings if embeddings is not None else [None] * len(normalized_chunks)
        if len(embeddings) != len(normalized_chunks):
            raise ValueError("Every stored document chunk must have one embedding slot.")
        for index, ((page, content), embedding) in enumerate(zip(normalized_chunks, embeddings)):
            connection._connection.execute(
                models.DocumentChunk.__table__.insert().values(document_id=document["id"], chunk_index=index, source_page=page, content=content, embedding=embedding)
            )
        connection.executemany("""INSERT INTO extracted_entities(document_id,entity_type,entity_value,normalized_value,source_page,confidence,context)
               VALUES(:document_id,:entity_type,:entity_value,:normalized_value,:source_page,:confidence,:context)""", [dict(item, document_id=document["id"]) for item in entities])
        connection.executemany("""INSERT INTO extracted_events(id,document_id,well_id,well_code,depth_start,depth_end,formation,event_type,severity,description,cause,mitigation,source_page,extraction_method,extraction_confidence,review_status)
               VALUES(:id,:document_id,:well_id,:well_code,:depth_start,:depth_end,:formation,:event_type,:severity,:description,:cause,:mitigation,:source_page,:extraction_method,:extraction_confidence,:review_status)""", [dict(item, document_id=document["id"]) for item in extracted_events])


def get_documents() -> list[Record]:
    return rows("""SELECT d.id,d.original_name,d.media_type,d.extension,d.size_bytes,d.extraction_status,d.extraction_note,d.created_at,w.well_code,
                  (SELECT COUNT(*) FROM extracted_entities x WHERE x.document_id=d.id) AS entity_count,
                  (SELECT COUNT(*) FROM extracted_events e WHERE e.document_id=d.id) AS extracted_event_count
           FROM documents d LEFT JOIN wells w ON w.id=d.well_id ORDER BY d.created_at DESC,d.id DESC""")


def get_document(document_id: str) -> Record | None:
    return row("SELECT * FROM documents WHERE id=?", (document_id,))


def get_document_chunks() -> list[Record]:
    return rows("""SELECT d.id,d.original_name,d.extraction_status,d.extraction_note,d.well_id,w.well_code,c.chunk_index,c.source_page,c.content
           FROM document_chunks c JOIN documents d ON d.id=c.document_id LEFT JOIN wells w ON w.id=d.well_id ORDER BY d.created_at DESC,c.chunk_index""")


def search_document_chunks(query: str, limit: int = 200) -> list[Record]:
    tokens = re.findall(r"[A-Za-z0-9]+", str(query or ""))
    if not tokens:
        return []
    if not is_postgres():
        normalized = [token.lower() for token in tokens if len(token) > 1]
        matches = []
        for chunk in get_document_chunks():
            content = str(chunk["content"] or "").lower()
            matched = sum(1 for token in normalized if token in content)
            if normalized and matched:
                chunk["lexical_rank"] = matched / len(normalized)
                matches.append(chunk)
        matches.sort(key=lambda item: (-item["lexical_rank"], item["id"], item["chunk_index"]))
        return matches[:max(1, min(int(limit), 500))]
    return rows("""SELECT d.id,d.original_name,d.extraction_status,d.extraction_note,d.well_id,w.well_code,c.chunk_index,c.source_page,c.content,
                  ts_rank_cd(to_tsvector('simple',c.content),plainto_tsquery('simple',?)) AS lexical_rank
           FROM document_chunks c JOIN documents d ON d.id=c.document_id LEFT JOIN wells w ON w.id=d.well_id
           WHERE to_tsvector('simple',c.content) @@ plainto_tsquery('simple',?)
           ORDER BY lexical_rank DESC,c.document_id,c.chunk_index LIMIT ?""", (query, query, max(1, min(int(limit), 500)))
    )


def search_similar_document_chunks(embedding: list[float], limit: int = 200) -> list[Record]:
    if not is_postgres() or not embedding:
        return []
    vector = "[" + ",".join(format(float(value), ".8g") for value in embedding) + "]"
    return rows("""SELECT d.id,d.original_name,d.extraction_status,d.extraction_note,d.well_id,w.well_code,c.chunk_index,c.source_page,c.content,
                  1-(c.embedding <=> CAST(? AS vector)) AS semantic_rank
           FROM document_chunks c JOIN documents d ON d.id=c.document_id LEFT JOIN wells w ON w.id=d.well_id
           WHERE c.embedding IS NOT NULL ORDER BY c.embedding <=> CAST(? AS vector) LIMIT ?""", (vector, vector, max(1, min(int(limit), 500)))
    )


def document_search_index_available() -> bool:
    return is_postgres()


def vector_search_available() -> bool:
    if not is_postgres():
        return False
    return bool(row("SELECT EXISTS(SELECT 1 FROM document_chunks WHERE embedding IS NOT NULL) AS available")["available"])


def get_document_extractions(document_id: str) -> dict[str, list[Record]]:
    return {
        "entities": rows("SELECT entity_type,entity_value,normalized_value,source_page,confidence,context FROM extracted_entities WHERE document_id=? ORDER BY id", (document_id,)),
        "events": rows("""SELECT e.*,d.original_name AS source_document,w.well_code AS linked_well_code FROM extracted_events e
               JOIN documents d ON d.id=e.document_id LEFT JOIN wells w ON w.id=e.well_id
               WHERE e.document_id=? ORDER BY e.source_page,e.depth_start""", (document_id,)),
    }


def get_extracted_events() -> list[Record]:
    return rows("""SELECT e.*,d.original_name AS source_document,w.well_code AS linked_well_code FROM extracted_events e
           JOIN documents d ON d.id=e.document_id LEFT JOIN wells w ON w.id=e.well_id
           WHERE d.extraction_status='ready' ORDER BY e.created_at DESC,e.source_page,e.depth_start""")


def get_well_context(well_id: int) -> dict[str, list[Record]]:
    return {
        "reservoir_properties": rows("SELECT * FROM reservoir_properties WHERE well_id=? ORDER BY depth_start", (well_id,)),
        "mud_programs": rows("SELECT * FROM mud_programs WHERE well_id=? ORDER BY depth_start", (well_id,)),
        "casing_programs": rows("SELECT * FROM casing_programs WHERE well_id=? ORDER BY setting_depth", (well_id,)),
        "cementing_records": rows("SELECT * FROM cementing_records WHERE well_id=? ORDER BY depth_start", (well_id,)),
    }


def get_alerts(well_code: str | None = None, statuses=()) -> list[Record]:
    clauses, params = [], []
    if well_code:
        clauses.append("w.well_code=?")
        params.append(well_code)
    if statuses:
        clauses.append("a.status IN (" + ",".join("?" for _ in statuses) + ")")
        params.extend(statuses)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return rows("SELECT a.*,w.well_code FROM alerts a JOIN wells w ON w.id=a.well_id" + where + " ORDER BY a.timestamp DESC,a.id DESC", params)


def upsert_alert(alert: dict[str, Any]) -> str:
    with connection_scope() as connection:
        active = connection.execute("SELECT id FROM alerts WHERE well_id=? AND risk_type=? AND status IN ('NEW','ACKNOWLEDGED') ORDER BY timestamp DESC LIMIT 1", (alert["well_id"], alert["risk_type"])).fetchone()
        if active:
            connection.execute("""UPDATE alerts SET prediction_id=?,timestamp=?,severity=?,confidence=?,trigger_reason=?,supporting_evidence=?,recommendation=? WHERE id=?""",
                (alert.get("prediction_id"), _dt(alert["timestamp"]), alert["severity"], alert["confidence"], alert["trigger_reason"], alert["supporting_evidence"], alert["recommendation"], active["id"]))
            return active["id"]
        values = dict(alert, timestamp=_dt(alert["timestamp"]))
        connection.execute("""INSERT INTO alerts(id,well_id,prediction_id,timestamp,risk_type,severity,confidence,trigger_reason,supporting_evidence,recommendation,status)
               VALUES(:id,:well_id,:prediction_id,:timestamp,:risk_type,:severity,:confidence,:trigger_reason,:supporting_evidence,:recommendation,'NEW')""", values)
        return alert["id"]


def update_alert_status(alert_id: str, status: str, timestamp: str) -> bool:
    if status not in {"ACKNOWLEDGED", "RESOLVED"}:
        raise ValueError("Alert status must be ACKNOWLEDGED or RESOLVED.")
    field = "acknowledged_at" if status == "ACKNOWLEDGED" else "resolved_at"
    with connection_scope() as connection:
        cursor = connection.execute("UPDATE alerts SET status=?," + field + "=? WHERE id=?", (status, _dt(timestamp), alert_id))
        return cursor.rowcount > 0


def get_model_versions() -> list[Record]:
    return rows("SELECT model_version,model_type,status,training_dataset_version,feature_names_json,metrics_json,artifact_path,note,created_at FROM model_versions ORDER BY created_at DESC,model_version")
