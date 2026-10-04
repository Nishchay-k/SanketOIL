"""Explainable geospatial retrieval and evidence-based risk scoring."""

import math
import re

from . import embedding_service, store

SEARCH_SYNONYMS = {
    "mud loss": ("lost circulation", "partial losses", "reduced returns", "formation intake", "lcm"),
    "stuck pipe": ("overpull", "tight hole", "pipe stuck", "cuttings loading"),
    "kick": ("influx", "pit gain", "flow check", "pressure event", "overpressure"),
    "torque": ("drag", "high side force", "pickup weight", "slack off"),
    "cement": ("casing", "cement returns", "slurry volume", "top up"),
    "overpressure": ("pore pressure", "pressure transition", "influx", "pit gain", "gas show"),
    "fishing": ("fish", "fishing operation", "retrieval operation", "lost in hole"),
    "shale swelling": ("swelling shale", "reactive shale", "wellbore instability", "tight hole"),
}
SEARCH_STOP_WORDS = {"a", "an", "and", "at", "by", "for", "from", "in", "is", "m", "near", "of", "on", "or", "the", "to", "well", "with"}

RISK_LABELS = {
    "MUD_LOSS": "Mud loss",
    "STUCK_PIPE": "Stuck pipe",
    "KICK_PRESSURE": "Kick / pressure",
    "TORQUE_DRAG": "Torque & drag",
    "CEMENTING": "Cementing",
    "OVERPRESSURE": "Formation pressure",
}

RECOMMENDATIONS = {
    "MUD_LOSS": "Review current returns, pit-volume trend, and ECD. Compare the mud program with the cited offset intervals before proceeding.",
    "STUCK_PIPE": "Review pickup/slack-off weight, hole-cleaning indicators, and the offset mitigations before the next connection or trip.",
    "KICK_PRESSURE": "Confirm flow and pit-volume status using the well-control procedure and review the cited pressure indicators.",
    "TORQUE_DRAG": "Compare torque, drag, and survey trends with the offset section. Review the planned operating window with the drilling team.",
    "CEMENTING": "Review the offset cement volumes, returns, and recorded top-up actions during the casing-program review.",
    "OVERPRESSURE": "Review the pressure-related offset records and compare the active mud program with the documented interval before proceeding.",
}

RISK_EVENT_TYPES = {
    "MUD_LOSS": {"MUD_LOSS"},
    "STUCK_PIPE": {"STUCK_PIPE"},
    "KICK_PRESSURE": {"KICK_PRESSURE"},
    "TORQUE_DRAG": {"TORQUE_DRAG"},
    "CEMENTING": {"CEMENTING"},
    "OVERPRESSURE": {"OVERPRESSURE", "KICK_PRESSURE"},
}


def distance_km(lat_a, lon_a, lat_b, lon_b):
    """Great-circle fallback for test engines without PostGIS distances."""
    radius = 6371.0088
    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    delta_phi = math.radians(lat_b - lat_a)
    delta_lambda = math.radians(lon_b - lon_a)
    value = math.sin(delta_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


def _depth_gap(depth, start, end):
    if start <= depth <= end:
        return 0.0
    return min(abs(depth - start), abs(depth - end))


def rank_offsets(active, radius_km, depth=None, formation=None):
    if depth is None:
        depth = active.get("current_depth") or 0
    formation = formation or active.get("formation")
    candidates = []
    postgis_candidates = store.get_nearby_wells(active["well_code"], radius_km)
    possible_wells = postgis_candidates if postgis_candidates is not None else store.get_wells()
    for well in possible_wells:
        if well["well_code"] == active["well_code"]:
            continue
        distance = well.get("distance_km")
        if distance is None:
            distance = distance_km(active["latitude"], active["longitude"], well["latitude"], well["longitude"])
        if distance > radius_km:
            continue
        well_events = store.get_events("e.well_id = ?", (well["id"],))
        relevant = [
            event for event in well_events
            if event["formation"] == formation and _depth_gap(depth, event["depth_start"], event["depth_end"]) <= 200
        ]
        same_formation = well["formation"] == formation or bool(relevant)
        geo_score = max(0.0, 1 - distance / radius_km)
        if relevant:
            nearest_gap = min(_depth_gap(depth, event["depth_start"], event["depth_end"]) for event in relevant)
            depth_score = max(0.0, 1 - nearest_gap / 200)
            event_score = min(1.0, len(relevant) / 3)
        else:
            depth_score = max(0.0, 1 - abs(depth - well["total_depth"]) / 1200)
            event_score = 0.0
        formation_score = 1.0 if same_formation else 0.35
        score = 0.25 * geo_score + 0.30 * formation_score + 0.25 * depth_score + 0.20 * event_score
        candidates.append({
            **well,
            "distance_km": round(distance, 1),
            "similarity": round(score, 3),
            "score_breakdown": {
                "geography": round(geo_score, 3),
                "formation": round(formation_score, 3),
                "depth": round(depth_score, 3),
                "event_history": round(event_score, 3),
            },
            "matched_formation": formation if same_formation else None,
            "matched_depth_interval": (
                [min(item["depth_start"] for item in relevant), max(item["depth_end"] for item in relevant)]
                if relevant else None
            ),
            "event_count": len(well_events),
            "relevant_event_count": len(relevant),
        })
    candidates.sort(key=lambda item: (-item["similarity"], item["distance_km"]))
    return candidates


def _telemetry_signals(well_id):
    readings = store.get_parameters(well_id, 2)
    if not readings:
        return {}
    current = readings[0]
    previous = readings[1] if len(readings) > 1 else None
    delta_pit = current["pit_volume"] - previous["pit_volume"] if previous else 0
    flow_change = (current["flow_rate"] - previous["flow_rate"]) / previous["flow_rate"] if previous and previous["flow_rate"] else 0
    pressure_change = (current["standpipe_pressure"] - previous["standpipe_pressure"]) / previous["standpipe_pressure"] if previous and previous["standpipe_pressure"] else 0
    torque_ratio = current["torque"] / previous["torque"] if previous and previous["torque"] else 1
    programs = store.get_well_context(well_id)["mud_programs"]
    current_program = next((item for item in programs if item["depth_start"] <= current["depth"] <= item["depth_end"]), None)
    under_program = bool(current_program and current["mud_weight"] < current_program["mud_weight_min"])
    return {
        "MUD_LOSS": delta_pit <= -0.6 or flow_change <= -0.12,
        "STUCK_PIPE": current["rop"] < 6 and current["torque"] >= 14,
        "KICK_PRESSURE": delta_pit >= 0.6 or (pressure_change <= -0.15 and flow_change > -0.08),
        "TORQUE_DRAG": current["torque"] >= 18 or torque_ratio >= 1.35,
        "CEMENTING": False,
        # A pit-gain signal outside the documented development mud-weight range
        # is a review indicator, not a pore-pressure estimate.
        "OVERPRESSURE": delta_pit >= 0.6 and under_program,
    }


def _pressure_context(active, depth, formation, radius_km):
    evidence = []
    all_wells = {item["well_code"]: item for item in store.get_wells()}
    for event in store.get_events():
        if event["well_code"] == active["well_code"] or event["event_type"] not in {"KICK_PRESSURE", "OVERPRESSURE"} or event["formation"] != formation:
            continue
        offset = all_wells[event["well_code"]]
        distance = distance_km(active["latitude"], active["longitude"], offset["latitude"], offset["longitude"])
        gap = _depth_gap(depth, event["depth_start"], event["depth_end"])
        if distance <= radius_km and gap <= 200:
            evidence.append({
                "event_id": event["id"],
                "well_code": event["well_code"],
                "distance_km": round(distance, 1),
                "depth_start": event["depth_start"],
                "depth_end": event["depth_end"],
                "depth_gap_m": round(gap),
                "source_document": event["source_document"],
                "source_page": event["source_page"],
            })
    evidence.sort(key=lambda item: (item["depth_gap_m"], item["distance_km"]))
    current = store.get_parameters(active["id"], 1)
    current_mud = current[0]["mud_weight"] if current else None
    program = next((item for item in store.get_well_context(active["id"])["mud_programs"] if item["formation"] == formation and item["depth_start"] <= depth <= item["depth_end"]), None)
    if len(evidence) >= 3:
        level = "ELEVATED"
    elif evidence:
        level = "WATCH"
    else:
        level = "INSUFFICIENT_EVIDENCE"
    return {
        "label": "Development estimate",
        "level": level,
        "basis": "nearby pressure-related event records and the active well's documented development mud program",
        "pressure_event_count": len(evidence),
        "evidence": evidence[:8],
        "current_mud_weight": current_mud,
        "planned_mud_weight_min": program["mud_weight_min"] if program else None,
        "planned_mud_weight_max": program["mud_weight_max"] if program else None,
        "mud_weight_within_plan": bool(program and current_mud is not None and program["mud_weight_min"] <= current_mud <= program["mud_weight_max"]),
        "measured_ppfg_available": False,
        "note": "No measured pore-pressure or fracture-gradient curve is stored. This indicator is not a field-validated pressure estimate.",
    }


def calculate_risk(well_code, depth, formation=None, radius_km=25):
    active = store.get_well(well_code)
    if not active:
        return None
    formation = formation or active["formation"]
    all_events = store.get_events()
    offsets_by_code = {item["well_code"]: item for item in store.get_wells()}
    telemetry_flags = _telemetry_signals(active["id"])
    signals = []

    for risk_type, label in RISK_LABELS.items():
        evidence = []
        for event in all_events:
            if event["event_type"] not in RISK_EVENT_TYPES[risk_type] or event["well_code"] == well_code:
                continue
            if event["formation"] != formation:
                continue
            offset = offsets_by_code[event["well_code"]]
            distance = distance_km(active["latitude"], active["longitude"], offset["latitude"], offset["longitude"])
            gap = _depth_gap(depth, event["depth_start"], event["depth_end"])
            if distance > radius_km or gap > 150:
                continue
            depth_fit = max(0.0, 1 - gap / 150)
            geographic_fit = max(0.0, 1 - distance / radius_km)
            relevance = 0.45 * depth_fit + 0.35 * geographic_fit + 0.20
            reason = (
                "Same formation; "
                + ("depth interval overlaps the current depth." if gap == 0 else str(round(gap)) + " m from the current depth.")
            )
            evidence.append({
                **event,
                "event_id": event["id"],
                "distance_km": round(distance, 1),
                "depth_gap_m": round(gap),
                "relevance": round(relevance, 3),
                "reason": reason,
            })
        evidence.sort(key=lambda item: (-item["relevance"], item["distance_km"]))

        count = len(evidence)
        average_depth_fit = sum(max(0, 1 - item["depth_gap_m"] / 150) for item in evidence) / count if count else 0
        average_geo_fit = sum(max(0, 1 - item["distance_km"] / radius_km) for item in evidence) / count if count else 0
        telemetry_flag = bool(telemetry_flags.get(risk_type))
        score_components = {
            "event_count": round(0.10 * min(count, 4), 3),
            "depth_fit": round(0.11 * average_depth_fit, 3),
            "formation_match": 0.08 if count else 0.0,
            "geographic_fit": round(0.05 * average_geo_fit, 3),
            "telemetry_indicator": 0.10 if telemetry_flag else 0.0,
        }
        if count:
            score_components["base"] = 0.30
        score = sum(score_components.values())
        confidence = 0.36 + 0.11 * min(count, 4) + 0.15 * average_depth_fit + 0.05 * average_geo_fit if count else (0.38 if telemetry_flag else 0.0)
        confidence = min(0.90, confidence + (0.05 if telemetry_flag and count else 0))
        score = round(min(0.97, score), 2)
        confidence = round(confidence, 2)
        severity = "HIGH" if score >= 0.78 else "MEDIUM" if score >= 0.55 else "LOW" if count or telemetry_flag else "UNKNOWN"
        signals.append({
            "risk_type": risk_type,
            "label": label,
            "score": score,
            "confidence": confidence,
            "severity": severity,
            "evidence_count": count,
            "telemetry_signal": telemetry_flag,
            "score_components": score_components,
            "average_depth_fit": round(average_depth_fit, 3),
            "average_geographic_fit": round(average_geo_fit, 3),
            "evidence": evidence[:8],
        })

    signals.sort(key=lambda item: (-item["score"], -item["confidence"], item["risk_type"]))
    primary = next((item for item in signals if item["evidence_count"] or item["telemetry_signal"]), None)
    if primary:
        evidence = primary["evidence"]
        unique_wells = len({item["well_code"] for item in evidence})
        if evidence:
            low = min(item["depth_start"] for item in evidence)
            high = max(item["depth_end"] for item in evidence)
            explanation = (
                str(unique_wells) + " nearby offset well" + ("" if unique_wells == 1 else "s")
                + " recorded " + primary["label"].lower() + " between "
                + format(round(low), ",") + " and " + format(round(high), ",")
                + " m in formation " + formation + ". The active well is at "
                + format(round(depth), ",") + " m."
            )
        else:
            explanation = "Current telemetry crossed a configured indicator for " + primary["label"].lower() + "; no matching offset event was found in the selected interval."
        if primary["telemetry_signal"] and evidence:
            explanation += " Current telemetry also shows a related change."
        recommendation = RECOMMENDATIONS[primary["risk_type"]]
        event_refs = evidence
    else:
        primary = {
            "risk_type": "UNKNOWN",
            "label": "No significant signal",
            "score": 0.0,
            "confidence": 0.0,
            "severity": "UNKNOWN",
            "evidence_count": 0,
            "telemetry_signal": False,
        }
        explanation = "No nearby same-formation event was found within 150 m of this depth, and the latest telemetry does not cross a configured indicator."
        recommendation = "Continue monitoring the available drilling indicators. Recheck after the next telemetry update or when the formation interpretation changes."
        event_refs = []

    pressure_context = _pressure_context(active, depth, formation, radius_km)
    return {
        "well_code": well_code,
        "well_name": active["name"],
        "depth": depth,
        "formation": formation,
        "risk_type": primary["risk_type"],
        "risk_label": primary["label"],
        "risk_score": primary["score"],
        "confidence": primary["confidence"],
        "severity": primary["severity"],
        "evidence_count": primary["evidence_count"],
        "explanation": explanation,
        "recommended_review": recommendation,
        "signals": signals,
        "evidence": event_refs,
        "pressure_context": pressure_context,
        "model_version": "rules-offset-v1.1",
        "data_quality": {
            "telemetry_available": bool(store.get_parameters(active["id"], 1)),
            "formation_match_required": True,
            "offset_radius_km": radius_km,
            "depth_window_m": 150,
            "supporting_event_count": len(event_refs),
            "pressure_measurement_available": False,
        },
    }


def search_evidence(query, limit=20):
    """Hybrid structured and text retrieval, with optional local embeddings."""
    query = re.sub(r"\s+", " ", str(query or "")).strip()
    if not query:
        return {"query": "", "engine": "structured+keyword-fallback-v2", "semantic_available": embedding_service.available(), "count": 0, "results": []}

    query_lower = query.lower()
    query_tokens = {token for token in re.findall(r"[a-z0-9]+", query_lower) if token not in SEARCH_STOP_WORDS}
    well_code_match = re.search(r"\b[A-Z]{1,3}-\d{2,5}\b", query.upper())
    if well_code_match:
        query_tokens.difference_update(re.findall(r"[a-z0-9]+", well_code_match.group(0).lower()))
    expanded_tokens = set(query_tokens)
    for key, phrases in SEARCH_SYNONYMS.items():
        if key in query_lower or any(phrase in query_lower for phrase in phrases):
            expanded_tokens.update(re.findall(r"[a-z0-9]+", key))
            for phrase in phrases:
                expanded_tokens.update(re.findall(r"[a-z0-9]+", phrase))

    depth_matches = [float(value.replace(",", "")) for value in re.findall(r"\b(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{3,4}(?:\.\d+)?)\s*(?:m|metres?|meters?)\b", query_lower)]
    formation_match = re.search(r"\bF\d{1,2}\b", query.upper())
    severity_match = next((value for value in ("HIGH", "MEDIUM", "LOW") if re.search(r"\b" + value + r"\b", query.upper())), None)
    event_type_match = None
    for event_type, phrases in {
        "MUD_LOSS": SEARCH_SYNONYMS["mud loss"],
        "STUCK_PIPE": SEARCH_SYNONYMS["stuck pipe"],
        "KICK_PRESSURE": SEARCH_SYNONYMS["kick"],
        "TORQUE_DRAG": SEARCH_SYNONYMS["torque"],
        "CEMENTING": SEARCH_SYNONYMS["cement"],
        "OVERPRESSURE": SEARCH_SYNONYMS["overpressure"],
    }.items():
        if event_type.replace("_", " ").lower() in query_lower or any(phrase in query_lower for phrase in phrases):
            event_type_match = event_type
            break

    def score_text(text, exact_fields=""):
        normalized = (str(text or "") + " " + str(exact_fields or "")).lower()
        tokens = set(re.findall(r"[a-z0-9]+", normalized))
        direct = len(query_tokens & tokens)
        expanded = len((expanded_tokens - query_tokens) & tokens)
        score = (direct / max(1, len(query_tokens))) * 0.68 + min(0.20, expanded * 0.05)
        if len(query_lower) >= 4 and query_lower in normalized:
            score += 0.2
        if well_code_match and well_code_match.group(0).lower() in normalized:
            score += 0.95
        return min(1.0, score)

    candidates = []

    def append_candidate(candidate, searchable):
        candidate["lexical_score"] = round(max(0.0, min(1.0, candidate.pop("score", 0.0))), 4)
        candidate["_search_text"] = searchable
        candidates.append(candidate)

    for well in store.get_wells():
        searchable = " ".join(str(well.get(key) or "") for key in ("well_code", "name", "field", "formation", "status"))
        score = score_text(searchable)
        if formation_match and well["formation"] == formation_match.group(0):
            score += 0.12
        if score >= 0.12:
            append_candidate({
                "kind": "well", "id": well["well_code"], "title": well["well_code"] + " · " + well["name"],
                "subtitle": well["field"] + " · " + well["formation"] + " · " + format(well["total_depth"], ",.0f") + " m",
                "snippet": "Well record with location, formation, status, and survey details.", "score": score,
                "well_code": well["well_code"],
            }, searchable)

    def event_candidate(event, extracted=False):
        code = event.get("well_code") or event.get("linked_well_code") or ""
        event_type = event.get("event_type", "")
        searchable = " ".join(str(event.get(key) or "") for key in ("well_code", "linked_well_code", "formation", "event_type", "severity", "description", "cause", "mitigation", "source_document", "original_name"))
        score = score_text(searchable)
        if formation_match and event.get("formation") == formation_match.group(0):
            score += 0.16
        if depth_matches and event.get("depth_start") is not None and event.get("depth_end") is not None:
            gap = _depth_gap(depth_matches[0], event["depth_start"], event["depth_end"])
            score += max(0.0, 0.18 * (1 - gap / 500))
        if event_type_match and (event_type == event_type_match or event_type_match == "OVERPRESSURE" and event_type == "KICK_PRESSURE"):
            score += 0.20
        if severity_match and event.get("severity") == severity_match:
            score += 0.10
        if well_code_match and code == well_code_match.group(0):
            score += 0.3
        source_document = event.get("source_document") or event.get("original_name") or ""
        source_page = event.get("source_page")
        depth_text = "Depth not extracted" if event.get("depth_start") is None else format(event["depth_start"], ",.0f") + "–" + format(event["depth_end"], ",.0f") + " m"
        status = " · Extracted · review pending" if extracted else ""
        if score >= 0.12:
            append_candidate({
                "kind": "event", "id": event.get("id"),
                "title": event_type.replace("_", " ").title() + (" · " + code if code else " · extracted event"),
                "subtitle": depth_text + (" · " + event.get("formation", "") if event.get("formation") else "") + " · " + event.get("severity", "UNKNOWN") + status,
                "snippet": (event.get("description", "") + ((" Cause: " + event.get("cause")) if event.get("cause") else "") + ((" Mitigation: " + event.get("mitigation")) if event.get("mitigation") else ""))[:500],
                "score": score, "well_code": code, "source_document": source_document,
                "source_page": source_page, "review_status": event.get("review_status", "CONFIRMED"),
                "extraction_confidence": event.get("extraction_confidence"),
                "extracted": extracted, "document_id": event.get("document_id") if extracted else None,
            }, searchable)

    for event in store.get_events():
        event_candidate(event)
    for event in store.get_extracted_events():
        event_candidate(event, extracted=True)

    chunks_by_document = {}
    indexed_chunks = store.search_document_chunks(query + " " + " ".join(sorted(expanded_tokens)))
    query_embedding = embedding_service.encode_text(query)
    semantic_chunks = store.search_similar_document_chunks(query_embedding) if query_embedding else []
    if semantic_chunks:
        merged = {}
        for chunk in indexed_chunks + semantic_chunks:
            key = (chunk["id"], chunk["chunk_index"])
            current = merged.get(key)
            if current is None or float(chunk.get("semantic_rank", 0)) > float(current.get("semantic_rank", 0)):
                merged[key] = chunk
        searchable_chunks = list(merged.values())
    elif indexed_chunks and not embedding_service.available():
        searchable_chunks = indexed_chunks
    else:
        searchable_chunks = store.get_document_chunks()
    for chunk in searchable_chunks:
        document_id = chunk["id"]
        exact = " ".join((chunk.get("original_name", ""), chunk.get("well_code", "")))
        score = score_text(chunk["content"], exact)
        if formation_match and formation_match.group(0).lower() in chunk["content"].lower():
            score += 0.12
        if depth_matches:
            depths = [float(value.replace(",", "")) for value in re.findall(r"\b(\d{1,3}(?:,\d{3})+|\d{3,4})\s*(?:m|metres?|meters?)\b", chunk["content"], re.IGNORECASE)]
            if depths:
                score += max(0.0, 0.12 * (1 - min(abs(item - depth_matches[0]) for item in depths) / 500))
        current = chunks_by_document.get(document_id)
        if score >= 0.12 and (current is None or score > current["score"]):
            chunks_by_document[document_id] = {"chunk": chunk, "score": score}
    for document_id, item in chunks_by_document.items():
        chunk = item["chunk"]
        searchable = " ".join((chunk["content"], chunk["original_name"], chunk.get("well_code") or ""))
        append_candidate({
            "kind": "document", "id": document_id, "title": chunk["original_name"],
            "subtitle": "Uploaded document · " + chunk["extraction_status"] + (" · " + chunk["well_code"] if chunk.get("well_code") else ""),
            "snippet": chunk["content"][:380], "score": item["score"], "well_code": chunk.get("well_code"),
            "source_document": chunk["original_name"], "source_page": chunk.get("source_page"),
        }, searchable)

    semantic_scores = embedding_service.similarities(query, [item["_search_text"] for item in candidates])
    for index, item in enumerate(candidates):
        if semantic_scores is None:
            item["score"] = item["lexical_score"]
        else:
            semantic = max(0.0, min(1.0, semantic_scores[index]))
            item["semantic_score"] = round(semantic, 4)
            item["score"] = round(0.70 * item["lexical_score"] + 0.30 * semantic, 4)
        item.pop("_search_text", None)
    candidates.sort(key=lambda item: (-item["score"], {"event": 0, "document": 1, "well": 2}.get(item["kind"], 3), item["title"]))
    results = candidates[:max(1, min(int(limit), 30))]
    vector_retrieval = bool(semantic_chunks)
    engine = "structured+pgvector+postgres-fts-v3" if vector_retrieval else "structured+semantic+fts5-v2" if semantic_scores is not None else "structured+postgres-fts+keyword-v3" if indexed_chunks else "structured+keyword-fallback-v2"
    if results:
        answer = "Retrieved " + str(len(results)) + " source-linked result" + ("s" if len(results) != 1 else "") + " using well, depth, formation, event, and text matches. Review extracted events before treating them as confirmed history."
    else:
        answer = "No local evidence matched this query. Try a well code, formation, depth, or drilling symptom."
    return {
        "query": query, "engine": engine, "semantic_available": semantic_scores is not None or vector_retrieval,
        "document_index": "postgres-fts+pgvector" if vector_retrieval else "postgres-fts" if store.document_search_index_available() else "local-keyword-fallback",
        "structured_query": {"well_code": well_code_match.group(0) if well_code_match else None,
                             "formation": formation_match.group(0) if formation_match else None,
                             "depth_m": depth_matches[0] if depth_matches else None,
                             "event_type": event_type_match, "severity": severity_match},
        "answer": answer, "count": len(results), "results": results,
    }
