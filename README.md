# SANKET — Nearby Wells Intelligence System

SANKET is a decision-support prototype for drilling teams. It brings nearby-well information, historical drilling events, report evidence, and risk indicators into one workspace.

The project is built for [Smart India Hackathon problem statement 26121](https://www.sih.gov.in/sih2026PS), which asks for a nearby-well intelligence system to complement eRTMAC.

> **Sample data:** The included wells, events, and readings are fictional demonstration records. They are not Oil India Limited operational data.

## What it does

- Maps nearby wells and ranks them by distance, formation, depth, and recorded event history.
- Shows well surveys, drilling events, reservoir details, programs, and available telemetry.
- Compares offset wells and historical events by depth and formation.
- Searches wells, events, and extracted document text.
- Accepts PDF, DOCX, TXT, Markdown, CSV, JSON, LOG, PNG, JPG, JPEG, TIF, and TIFF documents.
- Extracts text and source-page references. Scanned PDFs and images can use OCR.
- Presents explainable risk indicators and alerts with supporting evidence.
- Streams telemetry and alert updates to the dashboard.

## How the intelligence works

- Well relevance is calculated from distance (25%), formation (30%), depth (25%), and event history (20%).
- Risk indicators use explainable rules based on historical events and available readings. They are not calibrated probabilities.
- Document processing extracts text and candidate entities for engineer review. Evidence links retain the source document and page when available.
- Keyword and PostgreSQL full-text search work by default. Optional semantic search uses a locally configured embedding model.
- Telemetry can be demonstrated locally. SANKET does not currently connect to a live Oil India eRTMAC or WITSML feed.
- SANKET supports engineering review; it does not control drilling equipment or replace operational procedures.

## Technology

| Area | Technology |
| --- | --- |
| User interface | React, TypeScript, Vite, Tailwind CSS |
| API | Python, FastAPI |
| Database | PostgreSQL, PostGIS, pgvector |
| Database access and schema changes | SQLAlchemy, Alembic |
| Authentication | Local demo mode; Supabase Auth is supported |
| Document storage | Local storage for development; Supabase Storage is supported |
| Live updates | Server-Sent Events (SSE) |

The React entry point mounts the current TypeScript dashboard through a compatibility module. Existing dashboard styling is maintained in CSS.

## Run the local demo

### With Docker

Install Docker Desktop, then run from the project folder:

```sh
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000). Compose starts the app and a local PostgreSQL database with PostGIS and pgvector, applies the schema migration, and loads fictional sample records.

The local demo login is prefilled:

- **ID:** `engineer@oilindia.demo`
- **Password:** `NWIS-demo-26121`

### Without Docker

Install Python 3.12 or newer, Node.js 20 or newer, and PostgreSQL with PostGIS and pgvector enabled.

1. Copy `.env.example` to `.env`. Set `DATABASE_URL` to your local PostgreSQL database.
2. Install dependencies:

   ```sh
   python -m pip install -r backend/requirements.txt
   npm ci
   ```

3. Create or update the database schema:

   ```sh
   python -m alembic upgrade head
   ```

4. Start the API in one terminal:

   ```sh
   python -m backend.app.main
   ```

5. Start the frontend in another terminal:

   ```sh
   npm run dev
   ```

Open [http://localhost:5173](http://localhost:5173). Vite forwards API requests to the local FastAPI service. The example configuration enables demo sign-in and fictional seed records.

## Project structure

```text
backend/
  app/                 FastAPI routes, data access, risk rules, search, and document processing
  migrations/          Alembic database migrations
frontend/
  src/                 React/Vite entry point, API client, and dashboard
data/sample/            Fictional CSV records for the demo
database/               PostgreSQL image used by local Docker Compose
scripts/                Data seeding, export, telemetry, and import utilities
tests/                  Backend regression tests
docs/                   Architecture, API, database, and demo guides
```

## Development commands

```sh
npm run dev
npm run typecheck
npm run build
python -m unittest discover -s tests -v
```

## Guides

- [Architecture](docs/architecture.md)
- [API routes](docs/api.md)
- [Database notes](docs/database.md)
- [Demo workflow](docs/demo.md)

## Current limitations

- The sample dataset is fictional; operational conclusions require approved, representative Oil India data.
- Live eRTMAC integration needs an authorized feed, credentials, and agreed field mappings.
- Risk indicators use rules. A production-trained and independently validated risk model is not included.
- OCR and extracted event candidates should be reviewed by an engineer, especially for poor-quality scans.
