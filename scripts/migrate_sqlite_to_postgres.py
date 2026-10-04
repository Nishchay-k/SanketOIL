"""Copy an existing SANKET SQLite database into the configured PostgreSQL database."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import BigInteger, DateTime, Integer, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import models, storage, store
from backend.app.settings import get_settings


def _local_document_path(stored_name: str) -> Path:
    candidate = Path(stored_name)
    if not candidate.is_absolute():
        candidate = storage.LOCAL_DOCUMENTS / Path(*Path(stored_name).parts)
    candidate = candidate.resolve()
    candidate.relative_to(storage.LOCAL_DOCUMENTS.resolve())
    return candidate


def migrate(source_path: Path) -> dict[str, int]:
    settings = get_settings()
    settings.validate()
    if store.engine().dialect.name != "postgresql":
        raise RuntimeError("DATABASE_URL must point to PostgreSQL for this migration.")
    if not source_path.is_file():
        raise FileNotFoundError("SQLite source database not found: " + str(source_path))

    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    copied: dict[str, int] = {}
    uploaded_objects: list[str] = []
    try:
        with sqlite3.connect(str(source_path)) as source:
            source.row_factory = sqlite3.Row
            with store.engine().begin() as destination:
                populated = [
                    table.name for table in models.Base.metadata.sorted_tables
                    if destination.scalar(text('SELECT EXISTS(SELECT 1 FROM "' + table.name + '" LIMIT 1)'))
                ]
                if populated:
                    raise RuntimeError(
                        "The PostgreSQL target must be empty before importing SQLite data. "
                        "Tables with data: " + ", ".join(populated)
                    )
                for table in models.Base.metadata.sorted_tables:
                    exists = source.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table.name,)
                    ).fetchone()
                    if not exists:
                        continue
                    source_columns = {
                        row[1] for row in source.execute('PRAGMA table_info("' + table.name + '")')
                    }
                    target_columns = {column.name for column in table.columns}
                    common_columns = source_columns & target_columns
                    rows = source.execute('SELECT * FROM "' + table.name + '"').fetchall()
                    count = 0
                    for source_row in rows:
                        values = {key: source_row[key] for key in common_columns}
                        for column in table.columns:
                            value = values.get(column.name)
                            if value is not None and isinstance(column.type, (BigInteger, Integer)):
                                values[column.name] = int(value)
                            elif value is not None and isinstance(column.type, DateTime) and isinstance(value, str):
                                values[column.name] = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        if table.name == "documents":
                            values.setdefault("storage_backend", "local")
                            if settings.storage_backend == "supabase":
                                old_name = values.get("stored_name")
                                local_file = _local_document_path(str(old_name or ""))
                                if not local_file.is_file():
                                    raise FileNotFoundError("Document bytes are missing: " + str(local_file))
                                object_key = str(values["id"]) + "/" + local_file.name
                                backend, stored_name = storage.save_document(
                                    object_key, local_file.read_bytes(), values.get("media_type") or "application/octet-stream"
                                )
                                uploaded_objects.append(object_key)
                                values["storage_backend"] = backend
                                values["stored_name"] = stored_name
                        insert_statement = insert(table).values(values).on_conflict_do_nothing()
                        result = destination.execute(insert_statement)
                        count += result.rowcount or 0
                    copied[table.name] = count

                destination.execute(text(
                    "UPDATE wells SET location=ST_SetSRID(ST_MakePoint(longitude,latitude),4326)::geography "
                    "WHERE location IS NULL"
                ))
                for table in models.Base.metadata.sorted_tables:
                    if "id" in table.c and isinstance(table.c.id.type, (BigInteger, Integer)) and table.c.id.autoincrement:
                        destination.execute(
                            text(
                                "SELECT setval(pg_get_serial_sequence(:table_name, 'id'), "
                                "COALESCE((SELECT MAX(id) FROM \"" + table.name + "\"), 1), "
                                "EXISTS(SELECT 1 FROM \"" + table.name + "\"))"
                            ),
                            {"table_name": table.name},
                        )
    except Exception:
        for object_key in uploaded_objects:
            storage.delete_document("supabase", object_key)
        raise
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=ROOT / "data" / "nwis.sqlite3")
    args = parser.parse_args()
    counts = migrate(args.source.resolve())
    print("SQLite import completed. Rows copied by table:")
    for table_name, count in counts.items():
        print(f"  {table_name}: {count}")


if __name__ == "__main__":
    main()
