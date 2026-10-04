# SANKET — Nearby Wells Intelligence System

SANKET helps drilling teams find nearby wells, compare historical events, review source documents, and follow live telemetry alongside an active well.

> **Data notice:** Included wells, events, and readings are fictional development data. They are not Oil India Limited operating records.

## Features

- Map nearby wells and rank them by distance, formation, depth, and recorded event history.
- Compare surveys, event intervals, reservoir context, mud and casing programs, and telemetry.
- Search wells, events, document text, and drilling symptoms with source links.
- Review explainable risk signals and alerts with their supporting evidence.
- Add wells and upload PDF, DOCX, TXT, CSV, JSON, and image documents.
- Keep extracted page references and mark detected event candidates as pending engineer review.
- Stream telemetry updates and alerts over Server-Sent Events (SSE).

## Run with Docker

Install Docker Desktop, then from the project folder run:

```sh
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000). Compose starts PostgreSQL with PostGIS and pgvector, runs the Alembic migration, and launches the FastAPI service with the built React frontend. Local Compose uses demo sign-in and synthetic development records.

Stop the services with `Ctrl+C`, or run `docker compose down`. The database and local documents remain in Docker volumes. `docker compose down -v` deletes those local volumes.

## Run without Docker

Use Python 3.12+, Node.js 20+, and a PostgreSQL database with PostGIS and pgvector enabled.

1. Copy `.env.example` to `.env` and set `DATABASE_URL` for your PostgreSQL database.
2. Install the dependencies:

   ```sh
   python -m pip install -r backend/requirements.txt
   npm ci
   ```

3. Create the database tables:

   ```sh
   python -m alembic upgrade head
   ```

4. Start the API in one terminal:

   ```sh
   python -m backend.app.main
   ```

5. Start Vite in another terminal:

   ```sh
   npm run dev
   ```

Vite runs at [http://localhost:5173](http://localhost:5173) and proxies API requests to port 8000. The default local settings seed fictional sample records. Set `SEED_DEMO_DATA=false` to use an empty database.

## Deploy to Render and Supabase

The included `render.yaml` deploys one Docker web service. FastAPI serves the Vite-built React assets and API from the same Render URL. Supabase supplies PostgreSQL, PostGIS, pgvector, Auth, and private document Storage.

1. Create a Supabase project and enable the `postgis` and `vector` extensions. Create a **private** Storage bucket named `sanket-documents`.
2. In Supabase's **Connect** dialog, copy the **Session pooler** connection string and set it as Render's `DATABASE_URL`. Render uses IPv4, while Supabase's direct database endpoint is IPv6 by default. The Session pooler supports persistent IPv4 backends. Keep its port and username as supplied and URL-encode reserved characters in the password. Production configuration requires encrypted PostgreSQL connections. See [Supabase connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres) and [Render's IPv4 network note](https://supabase.com/docs/guides/troubleshooting/supabase--your-network-ipv4-and-ipv6-compatibility).
3. Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY` in Render.
4. Apply the `render.yaml` blueprint. Render runs `alembic upgrade head` before deploy and checks `/healthz`.
5. Create authorized users in Supabase Auth. The production login uses Supabase email/password sign-in; the service validates the returned JWT on API requests.
6. If a separate frontend origin is used later, set `CORS_ORIGINS` to that exact origin. The included deployment serves frontend and API from the same origin.

Never put the service-role key or database password in frontend variables. Render secrets are configured as private environment variables. Copy `.env.example` for the full local configuration reference.

To import an existing SQLite database, point `DATABASE_URL` to the target PostgreSQL database, configure the appropriate storage mode, then run:

```sh
python scripts/migrate_sqlite_to_postgres.py path/to/nwis.sqlite3
```

When `STORAGE_BACKEND=supabase`, the importer copies each original local document into the configured private bucket and updates its database reference. It stops if any source document bytes are missing.

## Current intelligence behavior

- **Implemented now:** deterministic nearby-well scoring, keyword and PostgreSQL full-text search, optional local sentence-embedding retrieval with pgvector, document extraction/OCR hooks, and explainable event/telemetry risk rules.
- **Not implemented as production AI:** no hosted LLM, autonomous recommendations, trained drilling-risk model, or validated failure probabilities. pgvector works only when a compatible local embedding model is installed and configured. Without it, keyword and full-text search remain active.
- **Live data boundary:** SSE is implemented and development telemetry can be simulated. There is no connected eRTMAC/WITSML endpoint or approved field mapping in this repository.

Risk output supports engineering review. It does not control drilling equipment or replace operational procedures.

## Useful commands

```sh
npm run build
python -m unittest discover -s tests -v
python -m alembic upgrade head
```

The regression suite uses temporary SQLite databases only as a lightweight test fixture. Production data access uses PostgreSQL.

## Project guides

- [Architecture](docs/architecture.md)
- [API routes](docs/api.md)
- [Database and migration](docs/database.md)
- [Demo workflow](docs/demo.md)
