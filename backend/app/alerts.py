"""Evidence-linked review alerts generated from the local risk assessment."""

import json
import secrets
from datetime import datetime, timezone

from . import store

ALERT_SCORE_THRESHOLD = 0.55


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def evaluate(well_code, risk, prediction_id=None, timestamp=None):
    """Persist threshold-triggered alerts; repeated updates refresh open alerts."""
    active = store.get_well(well_code)
    if not active:
        return []
    now = timestamp or risk.get("created_at") or _now()
    for signal in risk.get("signals", []):
        score = float(signal.get("score", 0) or 0)
        if score < ALERT_SCORE_THRESHOLD or signal.get("severity") == "UNKNOWN":
            continue
        evidence = signal.get("evidence") or []
        type_label = signal.get("label", signal.get("risk_type", "risk")).lower()
        if signal.get("telemetry_signal") and evidence:
            reason = "Current telemetry crossed a configured indicator, with " + str(len(evidence)) + " nearby historical record(s) in the matched interval."
        elif signal.get("telemetry_signal"):
            reason = "Current telemetry crossed a configured indicator for " + type_label + "."
        else:
            reason = str(len(evidence)) + " nearby same-formation record(s) support review around " + format(risk.get("depth", 0), ",.0f") + " m."
        supporting = [{
            "event_id": item.get("event_id", item.get("id")),
            "well_code": item.get("well_code"),
            "depth_start": item.get("depth_start"),
            "depth_end": item.get("depth_end"),
            "formation": item.get("formation"),
            "source_document": item.get("source_document"),
            "source_page": item.get("source_page"),
            "reason": item.get("reason", ""),
        } for item in evidence]
        alert_id = "AL-" + secrets.token_hex(6).upper()
        store.upsert_alert({
            "id": alert_id,
            "well_id": active["id"],
            "prediction_id": prediction_id,
            "timestamp": now,
            "risk_type": signal["risk_type"],
            "severity": signal["severity"],
            "confidence": float(signal.get("confidence", 0) or 0),
            "trigger_reason": reason,
            "supporting_evidence": json.dumps(supporting, ensure_ascii=False, separators=(",", ":")),
            "recommendation": risk.get("recommended_review", "Review the supporting evidence with the drilling team."),
        })
    return list_alerts(well_code)


def list_alerts(well_code=None, status=None):
    statuses = (status.upper(),) if status else ()
    result = store.get_alerts(well_code, statuses)
    for item in result:
        try:
            item["supporting_evidence"] = json.loads(item["supporting_evidence"] or "[]")
        except (TypeError, json.JSONDecodeError):
            item["supporting_evidence"] = []
    return result


def update_status(alert_id, status):
    changed = store.update_alert_status(alert_id, status, _now())
    return store.row("SELECT a.*,w.well_code FROM alerts a JOIN wells w ON w.id=a.well_id WHERE a.id=?", (alert_id,)) if changed else None
