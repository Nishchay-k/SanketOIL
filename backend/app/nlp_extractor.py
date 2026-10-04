"""Deterministic, evidence-preserving extraction for local drilling reports.

This deliberately uses transparent domain rules. It does not invent missing
well, depth, formation, severity, cause, or mitigation values.
"""

import re
import uuid


EVENT_TERMS = {
    "MUD_LOSS": ("mud loss", "mud losses", "lost circulation", "partial loss", "partial losses", "reduced returns", "loss of returns", "formation intake"),
    "STUCK_PIPE": ("stuck pipe", "stuck string", "overpull", "tight hole", "cuttings loading", "pipe stuck"),
    "KICK_PRESSURE": ("kick", "influx", "pit gain", "flow check", "flow increase", "possible influx"),
    "OVERPRESSURE": ("overpressure", "over-pressured", "pore pressure", "pressure transition", "pressure anomaly"),
    "TORQUE_DRAG": ("torque spike", "torque increase", "torque rose", "high torque", "drag increased", "high side force"),
    "CEMENTING": ("cement returns", "cement displacement", "cementing", "cement volume", "slurry volume", "cement top-up", "cement top up"),
    "FISHING": ("fishing operation", "fishing job", "fish in hole", "fishing tools"),
    "NPT": ("non-productive time", "npt", "lost time", "downtime"),
}

SECTION_NAMES = {
    "WELL": ("well", "well identification", "well name"),
    "FORMATION": ("formation", "lithology", "geology"),
    "DRILLING_PARAMETERS": ("drilling parameters", "mud parameters", "mud properties", "drilling data"),
    "EVENT": ("event", "operational event", "npt", "daily report"),
    "CAUSE": ("cause", "reason", "root cause"),
    "MITIGATION": ("mitigation", "action taken", "remedial action", "lessons learned"),
    "CASING": ("casing program", "casing", "liner"),
    "CEMENTING": ("cementing", "cement job"),
    "RESERVOIR": ("reservoir", "formation pressure", "ppfg", "pressure data"),
}

DEPTH_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<start>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{3,4}(?:\.\d+)?)"
    r"(?:\s*(?:-|–|—|to|through)\s*(?P<end>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{3,4}(?:\.\d+)?))?"
    r"\s*(?:m\b|metres?\b|meters?\b)", re.IGNORECASE,
)
WELL_RE = re.compile(r"\b[A-Z]{1,3}-\d{2,5}\b", re.IGNORECASE)
FORMATION_RE = re.compile(r"\bF\d{1,2}\b", re.IGNORECASE)
SEVERITY_TERMS = (
    ("HIGH", ("high severity", "severe", "critical", "high")),
    ("MEDIUM", ("moderate", "medium", "med severity")),
    ("LOW", ("minor", "low severity", "low")),
)


def clean_text(text):
    text = str(text or "").replace("\x00", " ").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text)
    return text.strip()


def detect_sections(text):
    """Split labeled report sections while preserving their source text."""
    sections = []
    current = "GENERAL"
    lines = []
    lookup = {alias: name for name, aliases in SECTION_NAMES.items() for alias in aliases}
    for line in clean_text(text).splitlines():
        stripped = line.strip()
        heading = stripped.rstrip(":").strip().lower()
        matched = lookup.get(heading)
        if not matched:
            for alias, section in lookup.items():
                if re.match(r"^" + re.escape(alias) + r"\s*[:\-]", heading):
                    matched = section
                    stripped = re.sub(r"^" + re.escape(alias) + r"\s*[:\-]\s*", "", stripped, flags=re.IGNORECASE)
                    break
        if matched:
            if lines:
                sections.append({"section": current, "text": "\n".join(lines).strip()})
            current = matched
            lines = [stripped] if stripped else []
        elif stripped:
            lines.append(stripped)
    if lines:
        sections.append({"section": current, "text": "\n".join(lines).strip()})
    return sections


def _depths(text):
    values = []
    for match in DEPTH_RE.finditer(text):
        start = float(match.group("start").replace(",", ""))
        end = float((match.group("end") or match.group("start")).replace(",", ""))
        if start > end:
            start, end = end, start
        values.append((start, end, match.group(0)))
    return values


def _event_type(sentence):
    normalized = sentence.lower()
    candidates = []
    for event_type, phrases in EVENT_TERMS.items():
        if any(phrase in normalized for phrase in phrases):
            candidates.append(event_type)
    # A single sentence can match the broad phrase "pressure" and a kick.
    # Prefer the explicitly described operational event and keep one record.
    priority = {"MUD_LOSS": 0, "STUCK_PIPE": 1, "KICK_PRESSURE": 2, "OVERPRESSURE": 3, "TORQUE_DRAG": 4, "CEMENTING": 5, "FISHING": 6, "NPT": 7}
    return min(candidates, key=lambda item: priority[item]) if candidates else None


def _severity(text):
    lower = text.lower()
    for severity, phrases in SEVERITY_TERMS:
        if any(re.search(r"\b" + re.escape(phrase) + r"\b", lower) for phrase in phrases):
            return severity
    return "UNKNOWN"


def _field_value(lines, labels):
    for index, line in enumerate(lines):
        match = re.match(r"^\s*(?:" + "|".join(labels) + r")\s*[:\-]\s*(.*)$", line, re.IGNORECASE)
        if match and match.group(1).strip():
            return match.group(1).strip()
        if match and index + 1 < len(lines):
            return lines[index + 1].strip()
    return ""


def extract_page_entities(text, page_number, known_wells=()):
    text = clean_text(text)
    if not text:
        return []
    known = {str(value).upper() for value in known_wells}
    entities = []

    def add(kind, value, normalized=None, confidence=0.82, context=""):
        if value is None or not str(value).strip():
            return
        entities.append({
            "entity_type": kind,
            "entity_value": str(value).strip(),
            "normalized_value": str(normalized if normalized is not None else value).strip(),
            "source_page": page_number,
            "confidence": confidence,
            "context": context[:240],
        })

    for match in WELL_RE.finditer(text):
        code = match.group(0).upper()
        if not known or code in known:
            line = next((line for line in text.splitlines() if code in line.upper()), "")
            add("well", code, code, 0.96, line)
    for match in FORMATION_RE.finditer(text):
        code = match.group(0).upper()
        add("formation", code, code, 0.92, next((line for line in text.splitlines() if code in line.upper()), ""))
    for start, end, source in _depths(text):
        add("depth_interval" if start != end else "depth", source, str(start) + "-" + str(end) + " m", 0.9, source)

    numeric_patterns = (
        ("mud_weight", r"(?:mud\s*weight|mud\s*wt\.?|MW)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:sg|g/cm(?:3|³))?"),
        ("rop", r"\bROP\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:m/?hr|m/?h)?"),
        ("wob", r"\bWOB\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:klbf|kN)?"),
        ("rpm", r"\bRPM\s*[:=]?\s*(\d+(?:\.\d+)?)"),
        ("torque", r"\btorque\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:kN.?m|klbf.?ft)?"),
        ("standpipe_pressure", r"(?:standpipe\s*pressure|SPP|pressure)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:bar|psi|kPa)?"),
        ("flow_rate", r"(?:flow\s*rate|flow)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:m3/?min|m³/min|l/?s)?"),
        ("pit_volume", r"(?:pit\s*volume|pit\s*gain|pit)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:m3|m³|bbl)?"),
        ("porosity_percent", r"porosity\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%?"),
        ("permeability_md", r"permeability\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:mD|millidarcies)?"),
    )
    for kind, pattern in numeric_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            context = next((line for line in text.splitlines() if match.group(0).lower() in line.lower()), match.group(0))
            add(kind, match.group(0), match.group(1), 0.9, context)

    for match in re.finditer(r'\b(\d{1,2}(?:\s+\d+/\d+)?\s*(?:in(?:ch(?:es)?)?|"))\s+(?:casing|csg)\b', text, re.IGNORECASE):
        add("casing_size", match.group(1), match.group(1).strip(), 0.86, match.group(0))

    lithologies = ("sandstone", "shale", "limestone", "siltstone", "conglomerate", "dolomite", "coal", "basalt")
    for term in lithologies:
        if re.search(r"\b" + term + r"\b", text, re.IGNORECASE):
            add("lithology", term, term, 0.8, next((line for line in text.splitlines() if term in line.lower()), ""))
    indicators = ("gas show", "overpressure", "permeable", "porosity", "fractured", "shale swelling", "swelling shale", "npt", "fishing")
    for term in indicators:
        if term in text.lower():
            add("reservoir_or_operational_indicator", term, term, 0.78, next((line for line in text.splitlines() if term in line.lower()), ""))

    for severity in ("HIGH", "MEDIUM", "LOW"):
        for match in re.finditer(r"\b" + severity + r"\b", text, re.IGNORECASE):
            add("severity", match.group(0), severity, 0.88, next((line for line in text.splitlines() if match.group(0).lower() in line.lower()), ""))
    return entities


def extract_document(pages, known_wells=()):
    """Return page-linked entities and event candidates from extracted text."""
    entities = []
    events = []
    known = {str(code).upper() for code in known_wells}
    for page_number, raw_text in pages:
        text = clean_text(raw_text)
        if not text:
            continue
        page_no = int(page_number) if page_number else None
        page_entities = []
        sections = detect_sections(text)
        for section in sections:
            for entity in extract_page_entities(section["text"], page_no, known):
                entity["context"] = ("[" + section["section"] + "] " + entity["context"]).strip()[:240]
                page_entities.append(entity)
        entities.extend(page_entities)
        well_codes = [item["normalized_value"] for item in page_entities if item["entity_type"] == "well"]
        formations = [item["normalized_value"] for item in page_entities if item["entity_type"] == "formation"]
        page_depths = _depths(text)
        lines = text.splitlines()
        page_cause = _field_value(lines, ("cause", "reason", "root cause"))
        page_mitigation = _field_value(lines, ("mitigation", "action taken", "remedial action", "lesson learned"))
        sentences = [part.strip(" \t-•") for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip(" \t-•")]
        seen = set()
        for sentence in sentences:
            event_type = _event_type(sentence)
            if not event_type:
                continue
            depths = _depths(sentence) or page_depths
            start, end = (depths[0][0], depths[0][1]) if depths else (None, None)
            sentence_wells = [match.group(0).upper() for match in WELL_RE.finditer(sentence) if not known or match.group(0).upper() in known]
            well_code = sentence_wells[0] if sentence_wells else (well_codes[0] if len(set(well_codes)) == 1 else "")
            sentence_forms = [match.group(0).upper() for match in FORMATION_RE.finditer(sentence)]
            formation = sentence_forms[0] if sentence_forms else (formations[0] if len(set(formations)) == 1 else "")
            severity = _severity(sentence)
            key = (event_type, well_code, start, end, sentence.lower())
            if key in seen:
                continue
            seen.add(key)

            related = [candidate for candidate in sentences if candidate != sentence and (
                re.search(r"\b(cause|because|due to|reason|result of)\b", candidate, re.IGNORECASE)
                or re.search(r"\b(mitigat|treated|placed|reduced|circulated|worked the string|top.?up|remedial|adjusted)\w*\b", candidate, re.IGNORECASE)
            )]
            cause = page_cause or next((candidate for candidate in related if re.search(r"\b(cause|because|due to|reason|result of)\b", candidate, re.IGNORECASE)), "")
            mitigation = page_mitigation or next((candidate for candidate in related if re.search(r"\b(mitigat|treated|placed|reduced|circulated|worked the string|top.?up|remedial|adjusted)\w*\b", candidate, re.IGNORECASE)), "")
            confidence = 0.42 + (0.16 if start is not None else 0) + (0.1 if formation else 0) + (0.12 if well_code else 0) + (0.1 if cause else 0) + (0.1 if mitigation else 0)
            confidence = min(0.94, confidence)
            events.append({
                "id": "EX-" + uuid.uuid4().hex[:12].upper(),
                "well_id": None,
                "well_code": well_code,
                "depth_start": start,
                "depth_end": end,
                "formation": formation,
                "event_type": event_type,
                "severity": severity,
                "description": sentence[:1200],
                "cause": cause[:800],
                "mitigation": mitigation[:800],
                "source_page": page_no,
                "extraction_method": "deterministic_domain_nlp",
                "extraction_confidence": round(confidence, 2),
                "review_status": "PENDING",
            })
    return {"entities": entities, "events": events}
