# Demo workflow

The sample dataset contains 36 fictional wells across Duliajan, Naharkatiya, Moran, and Tengakhat. The default Operations view opens A-101 around 2,840 m in formation F3.

## Try the application

1. Start the project with `docker compose up --build` and open [http://localhost:8000](http://localhost:8000).
2. Sign in with the local demo credentials shown on the login screen.
3. Open Operations and inspect nearby wells. Select an offset to view its details and historical events.
4. Switch to the depth view to compare survey paths and event intervals.
5. Search for a well, event type, symptom, formation, depth, or uploaded report.
6. Add a well or upload a report. Review extracted event candidates and source-page references before accepting them.
7. Open Risk and Evidence to compare the explainable signals with the original source.
8. Use the development telemetry action or simulator to send readings and watch them arrive over SSE.

The familiar login credentials are only for local demo mode. Production Auth uses Supabase users and JWTs.

## What the results mean

Offset relevance combines distance (25%), formation (30%), depth (25%), and event history (20%). The API returns the four component scores alongside the total.

Risk indicators use event matching and transparent telemetry thresholds. They show the evidence that triggered the review prompt. Results are not calibrated probabilities, and there is no production-trained drilling-risk model. The pressure indicator is a development estimate; the data does not include measured PPFG curves.

Search uses structured matches and keywords. PostgreSQL full-text search is available with the standard deployment. Semantic vector retrieval only turns on when a local embedding model is supplied; SANKET does not generate AI-written answers.

## Data and integration boundary

Sample wells, reports, events, and readings are synthetic. Document extraction uses local PDF/DOCX/text parsers and OCR tools when installed. Unsupported or unreadable scans are marked for OCR instead of being treated as extracted content.

The telemetry endpoint and SSE stream work with development readings. The eRTMAC adapter defines an integration boundary only. A live OIL feed, credentials, and approved field mapping must be supplied separately.
