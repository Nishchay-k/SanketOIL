"""Regression coverage for SANKET's local evidence and alert paths."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from os import environ
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import jwt

from backend.app import alerts, correlation, intelligence, main, nlp_extractor, storage, store, telemetry_source
from backend.app.settings import get_settings, sqlalchemy_database_url


class IntelligenceUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="sanket-test-")
        store.configure_database("sqlite:///" + str(Path(self.temp_dir.name, "test.sqlite3")).replace("\\", "/"))
        self.previous_document_directory = storage.LOCAL_DOCUMENTS
        storage.LOCAL_DOCUMENTS = Path(self.temp_dir.name) / "documents"
        store.initialize()

    def tearDown(self):
        store.configure_database()
        storage.LOCAL_DOCUMENTS = self.previous_document_directory
        self.temp_dir.cleanup()

    def test_database_seeds_context_and_explicit_model_fallback(self):
        bootstrap = store.get_bootstrap_data()
        self.assertEqual(36, bootstrap["health"]["wells"])
        self.assertGreater(bootstrap["health"]["events"], 0)
        models = store.get_model_versions()
        self.assertTrue(any(item["status"] == "active-fallback" for item in models))
        active = store.get_well("A-101")
        context = store.get_well_context(active["id"])
        self.assertTrue(context["reservoir_properties"])
        self.assertTrue(context["mud_programs"])
        self.assertTrue(context["casing_programs"])

    def test_extraction_keeps_page_depth_event_and_cause(self):
        report = (
            "Well: A-101\nFormation: F3\nDepth: 2,840 m\n"
            "Event: HIGH mud loss at 2,840 m in F3. Returns reduced while drilling fractured sandstone.\n"
            "Cause: Losses while drilling fractured sandstone.\n"
            "Mitigation: Pumped LCM pill and monitored returns."
        )
        result = nlp_extractor.extract_document([(7, report)], ["A-101"])
        event = next(item for item in result["events"] if item["event_type"] == "MUD_LOSS")
        self.assertEqual("A-101", event["well_code"])
        self.assertEqual("F3", event["formation"])
        self.assertEqual((2840.0, 2840.0), (event["depth_start"], event["depth_end"]))
        self.assertEqual(7, event["source_page"])
        self.assertIn("fractured sandstone", event["cause"].lower())
        self.assertIn("LCM", event["mitigation"])

    def test_document_chunks_events_and_search_keep_source_page(self):
        active = store.get_well("A-101")
        pages = [(3, "Well A-101 F3 mud loss at 2,840 m in fractured sandstone. Pumped LCM.")]
        knowledge = nlp_extractor.extract_document(pages, ["A-101"])
        for event in knowledge["events"]:
            event["well_id"] = active["id"]
        text = pages[0][1]
        store.add_document(
            {
                "id": "DOC-TEST-1", "original_name": "daily-report.txt", "stored_name": "test.txt",
                "media_type": "text/plain", "extension": ".txt", "size_bytes": len(text),
                "extraction_status": "ready", "extraction_note": "test", "extracted_text": text,
                "entities_json": "{}", "well_id": active["id"],
            },
            [(3, text)], knowledge["entities"], knowledge["events"],
        )
        chunks = store.search_document_chunks("fractured sandstone")
        extractions = store.get_document_extractions("DOC-TEST-1")
        self.assertTrue(chunks)
        self.assertEqual(3, chunks[0]["source_page"])
        self.assertTrue(extractions["events"])
        self.assertEqual("PENDING", extractions["events"][0]["review_status"])
        self.assertEqual("daily-report.txt", extractions["events"][0]["source_document"])

    def test_document_upload_api_returns_source_linked_event_candidates(self):
        report = (
            "Well: A-101\nFormation: F3\nDepth: 2,840 m\n"
            "Event: HIGH mud loss at 2,840 m in F3.\n"
            "Cause: Losses while drilling fractured sandstone.\n"
            "Mitigation: Pumped LCM pill and monitored returns."
        )
        with TestClient(main.app) as client:
            response = client.post(
                "/api/documents",
                files={"file": ("WCR-A101.txt", report.encode(), "text/plain")},
            )
            payload = response.json()
            self.assertEqual(201, response.status_code)
            document_id = payload["document"]["id"]
            extraction_response = client.get("/api/documents/" + document_id + "/extractions")
            extraction = extraction_response.json()
            self.assertEqual(200, extraction_response.status_code)
            event = next(item for item in extraction["events"] if item["event_type"] == "MUD_LOSS")
            self.assertEqual("WCR-A101.txt", event["source_document"])
            self.assertEqual(1, event["source_page"])
            self.assertEqual("PENDING", event["review_status"])

    def test_fastapi_serves_health_nearby_risk_search_and_telemetry(self):
        with TestClient(main.app) as client:
            root_page = client.get("/")
            self.assertEqual(200, root_page.status_code)
            self.assertIn("Sanket", root_page.text)
            self.assertEqual(200, client.get("/runtime-config").status_code)
            self.assertEqual(200, client.get("/healthz").status_code)
            self.assertEqual(200, client.get("/api/bootstrap").status_code)

            nearby = client.get("/api/wells/nearby", params={"well_id": "A-101", "radius_km": 10})
            self.assertEqual(200, nearby.status_code)
            self.assertTrue(nearby.json()["wells"])

            search = client.get("/api/search", params={"q": "mud loss F3"})
            self.assertEqual(200, search.status_code)
            self.assertTrue(search.json()["results"])

            prediction = client.post("/api/risk/predict", json={"well_id": "A-101", "depth": 2840, "formation": "F3"})
            self.assertEqual(200, prediction.status_code)
            self.assertIn("evidence", prediction.json()["prediction"])

            reading = client.post("/api/telemetry", json={
                "well_id": "A-101", "depth": 2845, "formation": "F3", "rop": 17.6, "wob": 13.8,
                "rpm": 112, "torque": 13.1, "standpipe_pressure": 177, "mud_weight": 1.16,
                "flow_rate": 1.78, "pit_volume": 38.3,
            })
            self.assertEqual(200, reading.status_code)
            self.assertEqual(2845, reading.json()["reading"]["depth"])

    def test_supabase_mode_checks_bearer_tokens(self):
        settings = get_settings()
        previous = (settings.auth_mode, settings.supabase_url, settings.supabase_jwt_secret)
        settings.auth_mode = "supabase"
        settings.supabase_url = "https://example.supabase.co"
        settings.supabase_jwt_secret = "test-only-signing-secret-32-bytes"
        try:
            token = jwt.encode({
                "sub": "test-user",
                "aud": "authenticated",
                "iss": settings.supabase_url + "/auth/v1",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            }, settings.supabase_jwt_secret, algorithm="HS256")
            with TestClient(main.app) as client:
                self.assertEqual(401, client.get("/api/bootstrap").status_code)
                self.assertEqual(200, client.get("/api/bootstrap", headers={"Authorization": "Bearer " + token}).status_code)
        finally:
            settings.auth_mode, settings.supabase_url, settings.supabase_jwt_secret = previous

    def test_production_postgres_urls_use_psycopg_and_encrypted_connections(self):
        with patch.dict(environ, {"APP_ENV": "production"}):
            url = sqlalchemy_database_url("postgresql://db-user:db-password@db.example.test:5432/sanket")
            self.assertTrue(url.startswith("postgresql+psycopg://"))
            self.assertIn("sslmode=require", url)
            verified = sqlalchemy_database_url("postgres://db-user:db-password@db.example.test/sanket?sslmode=verify-full")
            self.assertIn("sslmode=verify-full", verified)

    def test_depth_formation_correlation_returns_development_sources(self):
        result = correlation.build("A-101", 2840, "F3", 10)
        self.assertEqual("development", result["dataset"])
        self.assertEqual("F3", result["formation"])
        self.assertTrue(result["offsets"])
        self.assertTrue(any(item["events"] for item in result["offsets"]))

    def test_unknown_risk_has_no_fabricated_confidence(self):
        result = intelligence.calculate_risk("A-101", 7900, "F1", 1)
        self.assertEqual("UNKNOWN", result["risk_type"])
        self.assertEqual(0.0, result["confidence"])

    def test_threshold_alert_is_persisted_and_can_be_acknowledged(self):
        risk = {
            "depth": 2840,
            "recommended_review": "Compare the cited offset interval.",
            "signals": [{
                "risk_type": "MUD_LOSS", "label": "Mud loss", "score": 0.72,
                "confidence": 0.64, "severity": "MEDIUM", "telemetry_signal": False,
                "evidence": [{"event_id": "DEV-E001", "well_code": "W-014", "depth_start": 2830,
                              "depth_end": 2850, "formation": "F3", "source_document": "DEV-DDR-014",
                              "source_page": 8, "reason": "same formation and depth"}],
            }],
        }
        # Omit the optional prediction link so the fixture only exercises alert persistence.
        created = alerts.evaluate("A-101", risk)
        self.assertEqual("NEW", created[0]["status"])
        self.assertEqual("DEV-E001", created[0]["supporting_evidence"][0]["event_id"])
        updated = alerts.update_status(created[0]["id"], "ACKNOWLEDGED")
        self.assertEqual("ACKNOWLEDGED", updated["status"])

    def test_development_telemetry_is_stamped_and_ertmac_is_only_an_adapter_contract(self):
        values = telemetry_source.DevelopmentTelemetrySource().normalize({"depth": 2800})
        self.assertEqual("development", values["source"])
        self.assertTrue(values["timestamp"].endswith("Z"))
        with self.assertRaises(RuntimeError):
            telemetry_source.ERTMACAdapter().normalize({"depth": 2800})


if __name__ == "__main__":
    unittest.main()
