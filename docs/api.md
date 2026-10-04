# API guide

FastAPI serves the API at `/api/*` and the built frontend at `/`. During development, Vite proxies API and runtime-configuration requests to FastAPI on port 8000.

## Authentication and errors

Local demo mode accepts requests without a token. Production uses Supabase Auth. Send the access token on protected requests:

```http
Authorization: Bearer <supabase-access-token>
```

`GET /healthz`, `GET /api/health`, and `GET /runtime-config` are public. Other API routes require a valid Supabase JWT in production. Never put the Supabase service-role key in the browser.

API errors use a simple shape:

```json
{"error":{"message":"Human-readable explanation","status":422}}
```

## Health and reference data

| Route | Purpose |
| --- | --- |
| `GET /healthz` | Deployment check; verifies database connectivity and reports 503 if unavailable. |
| `GET /api/health` | Database status, dataset label, and record counts. |
| `GET /runtime-config` | Public browser settings such as Auth mode and Supabase URL/anon key. |
| `GET /api/bootstrap` | Wells, formation intervals, and counts for the initial page load. |
| `GET /api/formations` | Formation names and depth ranges. |
| `GET /api/models` | Active rule and development-model descriptions. |

## Wells, events, and evidence

| Route | Purpose |
| --- | --- |
| `GET /api/wells` | List wells. Supports `field`, `status`, and text `q` filters. |
| `POST /api/wells` | Add a well with code, name, field, coordinates, depth, and formation. |
| `GET /api/wells/{well_code}` | Well details, surveys, events, recent readings, and stored context. |
| `GET /api/wells/nearby?well_id=A-101&radius_km=10&depth=2840&formation=F3` | Find nearby wells and return their relevance breakdown. |
| `GET /api/wells/{well_code}/events` | Events for a well, optionally filtered by depth, type, severity, or text. |
| `GET /api/events` | Search event history with well, formation, event, depth, severity, and text filters. |
| `GET /api/events/{event_id}` | One event and its source details. |
| `GET /api/search?q=mud%20loss%20F3%202840&limit=12` | Search structured well/event data and source-linked document text. |
| `GET /api/correlation?well_id=A-101&depth=2840&formation=F3&radius_km=10` | Compare offset context and trajectories at a depth interval. |

Nearby wells use PostGIS for the radius filter and distance. The existing application logic scores distance, formation, depth, and event history. Search keeps structured and keyword matching, PostgreSQL full-text search, and optional pgvector retrieval when local embeddings are present.

## Risk and alerts

Call `POST /api/risk/predict` with a JSON body such as:

```json
{"well_id":"A-101","depth":2840,"formation":"F3","radius_km":10}
```

The response includes explainable risk signals, evidence links, confidence, and review recommendations. `GET /api/risk/{prediction_id}` returns a saved prediction.

| Route | Purpose |
| --- | --- |
| `GET /api/alerts?well_id=A-101&status=NEW` | List alerts with source evidence. |
| `POST /api/alerts/{alert_id}/acknowledge` | Mark an alert acknowledged. |
| `POST /api/alerts/{alert_id}/resolve` | Mark an alert resolved. |

Risk is based on existing rules and historical events. It is not a trained or calibrated production predictor.

## Documents

| Route | Purpose |
| --- | --- |
| `GET /api/documents` | List uploaded documents, supported formats, size limit, and available extraction/search capabilities. |
| `POST /api/documents` | Upload multipart form data in the `file` field. |
| `GET /api/documents/{document_id}` | Document metadata and extraction details. |
| `GET /api/documents/{document_id}/extractions` | Extracted entities and event candidates with source pages and review status. |
| `GET /api/documents/{document_id}/download` | Local file response in development or a short-lived signed URL in Supabase mode. |

Supported formats include PDF, DOCX, TXT, Markdown, CSV, JSON, LOG, PNG, JPG, JPEG, TIF, and TIFF. The default limit is 12 MB. Page information is saved when available. OCR uses Tesseract; scanned PDFs also need PyMuPDF. Event candidates remain pending until an engineer reviews them.

## Telemetry

| Route | Purpose |
| --- | --- |
| `GET /api/telemetry?well_id=A-101` | Latest readings. |
| `POST /api/telemetry` | Add a validated reading. |
| `GET /api/telemetry/stream?well_id=A-101` | Receive telemetry and alert events as SSE. |

The browser uses an authenticated SSE client so Supabase bearer tokens are sent with the stream. The connection sends keepalives and reconnects. The development simulator is not connected to eRTMAC or a rig feed.

## Interactive API docs

In development mode, open `/api/docs` for Swagger UI or `/api/redoc` for ReDoc. These pages are disabled in production.
