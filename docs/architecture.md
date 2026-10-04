# Architecture

SANKET is a single deployable application. The frontend and API share one Render web service, with Supabase providing the managed database, authentication, and file storage.

```text
React + TypeScript + Vite + Tailwind
                 │ JSON, JWT, and SSE
                 ▼
              FastAPI
                 │ SQLAlchemy
                 ▼
PostgreSQL + PostGIS + pgvector  ──  Supabase Storage
```

The Vite build is copied into the FastAPI container. FastAPI serves the frontend and `/api/*` routes from one origin. During local development, Vite runs separately and proxies API calls to port 8000.

## Frontend

`frontend/src/main.tsx` starts the React application and loads runtime configuration from FastAPI. The existing screens are mounted through a TypeScript compatibility module so current layout and interactions continue to work during the migration. `frontend/src/lib/api.ts` handles API requests, Supabase sessions, bearer tokens, and authenticated SSE. Existing styles remain in place; Tailwind is available for incremental component work and its reset is disabled to avoid changing the established interface.

## API and business logic

`backend/app/main.py` defines FastAPI routes, validation, CORS, health checks, static assets, and telemetry streaming. SQLAlchemy models and the store module provide persistence. The ranking, correlation, extraction, alert, and risk modules remain separate so database and server changes do not replace their existing rules.

### Nearby-well ranking

PostGIS filters wells within the requested radius and calculates distance. Existing application scoring then ranks those wells using distance, formation, depth, and historical events. The API exposes the score breakdown for review.

### Risk and alerts

Risk signals come from explainable event matching and simple telemetry thresholds. Every available historical signal can link to the source event, report, and page. Results without support stay `UNKNOWN` with zero confidence. Threshold alerts are review prompts; they are not automated drilling instructions.

There is no validated production ML model in this repository. Model-version records identify rule and development indicators. Do not interpret scores as calibrated failure probabilities.

### Evidence search

Search combines structured fields, drilling-symptom terms, and document chunks. PostgreSQL full-text search remains available without an embedding model. If a local sentence-transformer model with the configured dimension is supplied, vectors are stored in pgvector and semantic candidates are combined with lexical matches. No hosted generative AI is called, and search does not invent answer text.

## Documents

PDF, DOCX, text, and supported image formats pass through the existing local extraction pipeline. PDF page numbers and source references are stored with text chunks and event candidates. OCR uses Tesseract; scanned-PDF processing also uses PyMuPDF. Missing OCR tools produce a `needs_ocr` status instead of pretending extraction succeeded. Supabase Storage holds uploaded bytes in production; a private bucket and signed download links are used.

Detected events remain pending engineer review and are stored separately from verified historical events.

## Authentication and configuration

Local development can use `AUTH_MODE=demo`. Production validation requires Supabase Auth configuration and Supabase Storage. In Supabase mode, the browser signs in with the public anon key and sends the access token; FastAPI verifies the JWT using Supabase signing keys (or the configured legacy JWT secret). Keep service-role and database credentials on the server only.

Settings load from environment variables and a local `.env` file. `.env.example` contains local defaults; `render.yaml` defines production-safe switches with secret values set in the Render dashboard.

## Telemetry

`POST /api/telemetry` stores validated readings and the browser receives changes through SSE at `/api/telemetry/stream`. The stream keeps reconnect behavior and sends alert events. The included simulator is development data. `ERTMACAdapter` is only a future integration boundary; live eRTMAC/WITSML connectivity, credentials, and field mapping are not included.

## Deployment

Docker builds the Vite assets, installs the Python API, and runs as a non-root user. Render runs Alembic before deploy and checks `/healthz`. Production disables automatic schema creation and demo seeding. Supabase hosts PostgreSQL with PostGIS and pgvector extensions, Auth, and the private document bucket.

The current container serves frontend and API from one Render service. If the frontend is later split into a separate static site, set `CORS_ORIGINS` to that exact site URL.
