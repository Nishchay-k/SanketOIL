"""Depth-, formation-, and distance-aware well context assembled from the store."""

from . import intelligence, store


PARAMETER_TOLERANCES = {
    "rop": 10.0,
    "wob": 10.0,
    "rpm": 60.0,
    "torque": 12.0,
    "standpipe_pressure": 80.0,
    "mud_weight": 0.25,
    "flow_rate": 1.0,
    "pit_volume": 12.0,
}


def _interval_matches(item, depth, formation):
    return item.get("formation") == formation and item.get("depth_start", 0) <= depth <= item.get("depth_end", 0)


def _context_at_depth(well_id, depth, formation):
    context = store.get_well_context(well_id)
    return {
        "reservoir_properties": [item for item in context["reservoir_properties"] if _interval_matches(item, depth, formation)],
        "mud_programs": [item for item in context["mud_programs"] if _interval_matches(item, depth, formation)],
        "casing_programs": [item for item in context["casing_programs"] if item["setting_depth"] <= depth],
        "cementing_records": [item for item in context["cementing_records"] if item.get("formation") == formation and (item.get("depth_start") is None or item["depth_start"] <= depth + 200) and (item.get("depth_end") is None or item["depth_end"] >= depth - 200)],
    }


def _parameter_comparison(current, offset):
    comparisons = {}
    if not current or not offset:
        return {"values": comparisons, "similarity": None}
    scores = []
    for key, tolerance in PARAMETER_TOLERANCES.items():
        if current.get(key) is None or offset.get(key) is None:
            continue
        delta = float(offset[key]) - float(current[key])
        similarity = max(0.0, 1.0 - abs(delta) / tolerance)
        scores.append(similarity)
        comparisons[key] = {"active": current[key], "offset": offset[key], "delta": round(delta, 3), "similarity": round(similarity, 3)}
    return {"values": comparisons, "similarity": round(sum(scores) / len(scores), 3) if scores else None}


def build(well_code, depth, formation, radius_km=10):
    active = store.get_well(well_code)
    if not active:
        return None
    active_context = _context_at_depth(active["id"], depth, formation)
    current_readings = store.get_parameters(active["id"], 1)
    current_parameters = current_readings[0] if current_readings else None
    offsets = intelligence.rank_offsets(active, radius_km, depth, formation)
    events = store.get_events()
    comparisons = []
    for offset in offsets:
        offset_events = [event for event in events if event["well_code"] == offset["well_code"] and event["formation"] == formation and intelligence._depth_gap(depth, event["depth_start"], event["depth_end"]) <= 200]
        context = _context_at_depth(offset["id"], depth, formation)
        readings = store.get_parameters(offset["id"], 60)
        nearest_reading = min(readings, key=lambda item: abs(item["depth"] - depth)) if readings else None
        surveys = store.get_surveys(offset["id"])
        nearest_survey = min(surveys, key=lambda item: abs(item["measured_depth"] - depth)) if surveys else None
        if not offset_events and not any(context.values()):
            continue
        comparisons.append({
            "well_code": offset["well_code"],
            "name": offset["name"],
            "field": offset["field"],
            "distance_km": offset["distance_km"],
            "relevance": offset["similarity"],
            "depth_match": bool(offset_events or context["reservoir_properties"] or context["mud_programs"]),
            "events": offset_events,
            "reservoir_properties": context["reservoir_properties"],
            "mud_programs": context["mud_programs"],
            "casing_programs": context["casing_programs"],
            "cementing_records": context["cementing_records"],
            "nearest_survey": nearest_survey,
            "parameter_comparison": _parameter_comparison(current_parameters, nearest_reading),
        })
    return {
        "dataset": "development",
        "well_code": well_code,
        "depth": depth,
        "formation": formation,
        "radius_km": radius_km,
        "active_context": active_context,
        "offsets": comparisons,
        "correlation_method": "formation + measured-depth interval + Haversine radius + available parameter similarity",
        "note": "Context values are synthetic development records. Missing fields mean no structured record is available.",
    }
