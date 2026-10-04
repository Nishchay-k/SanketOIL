"""Coherent, synthetic development data for the NWIS demonstration."""

import math


FIELD_CENTERS = {
    "Duliajan": (27.3600, 95.3350),
    "Naharkatiya": (27.2880, 95.0450),
    "Moran": (27.1700, 94.9150),
    "Tengakhat": (27.2100, 95.1100),
}

# Coordinates are expressed as east/north offsets from each field center in km.
# The three F3 offset wells deliberately form the A-101 mud-loss demonstration.
WELL_GROUPS = {
    "Duliajan": [
        ("A-101", 0.0, 0.0, "F3", "drilling", 3240, 2840),
        ("W-014", 3.8, 1.1, "F3", "completed", 3370, None),
        ("W-021", 6.2, -1.4, "F3", "completed", 3290, None),
        ("W-031", -7.5, 2.0, "F3", "completed", 3410, None),
        ("W-003", 2.1, -2.7, "F2", "completed", 3160, None),
        ("W-006", -4.0, -3.8, "F4", "completed", 3520, None),
        ("W-008", 8.3, 1.0, "F4", "completed", 3480, None),
        ("W-011", 3.1, 5.2, "F2", "completed", 3090, None),
        ("W-017", -5.7, 4.5, "F4", "completed", 3550, None),
        ("W-019", 4.9, -4.5, "F2", "completed", 3220, None),
        ("W-024", -1.0, 8.2, "F3", "completed", 3350, None),
        ("W-027", -9.0, -1.4, "F1", "completed", 3010, None),
        ("W-030", 9.6, -4.0, "F4", "completed", 3610, None),
        ("W-034", 10.4, 1.1, "F3", "completed", 3300, None),
    ],
    "Naharkatiya": [
        ("N-101", 0.0, 0.0, "F3", "completed", 3360, None),
        ("N-102", 3.0, 1.5, "F2", "completed", 3180, None),
        ("N-108", -2.8, 2.4, "F4", "completed", 3490, None),
        ("N-112", 5.2, -2.1, "F3", "completed", 3320, None),
        ("N-115", -4.5, -3.0, "F2", "completed", 3120, None),
        ("N-118", 1.4, 5.5, "F4", "completed", 3510, None),
        ("N-121", -6.2, 1.0, "F3", "completed", 3270, None),
        ("N-124", 7.0, 3.8, "F1", "completed", 2980, None),
        ("N-127", 0.8, -6.5, "F4", "completed", 3440, None),
        ("N-130", -7.4, -4.1, "F2", "completed", 3160, None),
    ],
    "Moran": [
        ("M-201", 0.0, 0.0, "F3", "completed", 3310, None),
        ("M-205", 3.7, 2.0, "F4", "completed", 3570, None),
        ("M-208", -3.5, 2.8, "F2", "completed", 3200, None),
        ("M-212", 5.8, -2.4, "F3", "completed", 3390, None),
        ("M-216", -5.6, -2.0, "F4", "completed", 3480, None),
        ("M-219", 1.6, 6.1, "F2", "completed", 3140, None),
        ("M-223", -1.2, -6.7, "F3", "completed", 3290, None),
        ("M-229", 7.3, 4.0, "F1", "completed", 2960, None),
    ],
    "Tengakhat": [
        ("T-301", 0.0, 0.0, "F3", "completed", 3340, None),
        ("T-304", 3.5, -1.2, "F4", "completed", 3540, None),
        ("T-308", -3.2, 2.7, "F2", "completed", 3130, None),
        ("T-311", 5.6, 4.1, "F3", "completed", 3380, None),
    ],
}

FORMATIONS = [
    {"name": "F1", "top_depth": 0, "bottom_depth": 1200, "description": "Upper clastic section"},
    {"name": "F2", "top_depth": 1200, "bottom_depth": 2420, "description": "Middle sandstone and shale sequence"},
    {"name": "F3", "top_depth": 2420, "bottom_depth": 2960, "description": "Lower sandstone interval; loss evidence in nearby offsets"},
    {"name": "F4", "top_depth": 2960, "bottom_depth": 3800, "description": "Basement-proximal lower section"},
]

EVENT_SPECS = [
    ("W-014", 2830, 2860, "F3", "MUD_LOSS", "HIGH", "Partial mud loss while drilling a permeable F3 sandstone.", "Elevated equivalent circulating density across a fractured interval.", "Reduced pump rate and placed a staged LCM sweep; returns stabilized.", "W-014", 12),
    ("W-021", 2850, 2872, "F3", "MUD_LOSS", "MEDIUM", "Partial losses recorded across the lower F3 sandstone.", "Formation intake increased as the well entered a more permeable bed.", "Placed an LCM pill and confirmed returns before resuming drilling.", "W-021", 18),
    ("W-031", 2864, 2892, "F3", "MUD_LOSS", "HIGH", "Mud loss with reduced surface returns near the F3 lower contact.", "Fractured sandstone response during the interval transition.", "Reduced ECD, circulated a weighted LCM pill, and monitored pit volume.", "W-031", 9),
    ("W-003", 2510, 2534, "F3", "STUCK_PIPE", "MEDIUM", "Overpull increased after a short connection while drilling F3.", "Cuttings accumulation and a tight hole were noted in the daily report.", "Worked the string carefully and circulated a high-viscosity sweep.", "W-003", 22),
    ("W-006", 3020, 3044, "F4", "TORQUE_DRAG", "HIGH", "Sustained torque increase while drilling the upper F4 section.", "Abrupt lithology change with rising drag on the build section.", "Reduced WOB, reamed the interval, and checked the torque trend.", "W-006", 14),
    ("W-008", 3110, 3136, "F4", "KICK_PRESSURE", "HIGH", "Flow check identified a short-lived flow increase after a connection.", "Possible influx indicator during a pressure transition.", "Performed a flow check and verified pit-volume trend before proceeding.", "W-008", 7),
    ("W-011", 2398, 2420, "F2", "CEMENTING", "MEDIUM", "Cement returns were lower than the planned volume during casing.", "Loss of slurry volume across a permeable F2 string section.", "Recorded the shortfall and completed a documented top-up.", "W-011", 31),
    ("W-017", 3002, 3025, "F4", "MUD_LOSS", "MEDIUM", "Reduced returns observed near the F3/F4 transition.", "A narrow loss zone was reported at the formation boundary.", "Held depth and treated with a low-solids LCM blend.", "W-017", 16),
    ("W-019", 2490, 2518, "F3", "KICK_PRESSURE", "MEDIUM", "Standpipe pressure and flow readings prompted a connection flow check.", "Pressure response differed from the established drilling trend.", "Confirmed static conditions and reviewed the mud-weight margin.", "W-019", 11),
    ("W-024", 2794, 2818, "F3", "STUCK_PIPE", "LOW", "Drag increased during a short trip through the F3 interval.", "Cuttings loading was suspected after reduced circulation time.", "Circulated a sweep and monitored pickup weight.", "W-024", 24),
    ("W-030", 3210, 3238, "F4", "TORQUE_DRAG", "MEDIUM", "Intermittent torque peaks during a directional correction.", "Dogleg severity increased over the recorded survey interval.", "Reamed the section and reviewed the survey before continuing.", "W-030", 19),
    ("N-101", 2820, 2848, "F3", "MUD_LOSS", "MEDIUM", "Partial losses reported while drilling a lower F3 sandstone.", "Permeable bed intake with stable well-control indicators.", "Applied an LCM sweep and tracked returns through the next stand.", "N-101", 15),
    ("N-108", 3090, 3124, "F4", "TORQUE_DRAG", "MEDIUM", "Torque increased during a high-angle section in F4.", "Drag rose with inclination and sliding footage.", "Adjusted the rotary schedule and reamed before the next trip.", "N-108", 20),
    ("N-112", 2670, 2696, "F3", "STUCK_PIPE", "HIGH", "String movement slowed after a prolonged drilling interval.", "Cuttings bed and tight-hole signs were described in the report.", "Circulated bottoms-up and worked the pipe within operating limits.", "N-112", 13),
    ("N-115", 2376, 2404, "F2", "CEMENTING", "LOW", "Cement displacement finished below the planned return volume.", "Small slurry-volume shortfall during the casing job.", "Logged the final volumes and completed a verification top-up.", "N-115", 28),
    ("N-118", 3160, 3188, "F4", "KICK_PRESSURE", "MEDIUM", "Flow check requested after a modest pit gain at connection.", "Possible influx indicator; no sustained flow was confirmed.", "Held pumps, checked flow, and reviewed the trip margin.", "N-118", 8),
    ("M-201", 2826, 2854, "F3", "MUD_LOSS", "MEDIUM", "Returns reduced while drilling the lower F3 sandstone.", "Formation intake increased over a 28 m interval.", "Pumped a staged LCM blend and monitored the next connection.", "M-201", 17),
    ("M-205", 3150, 3182, "F4", "TORQUE_DRAG", "HIGH", "High torque persisted through a directional interval.", "Survey showed increasing inclination and contact length.", "Reduced WOB and reviewed the planned trajectory.", "M-205", 10),
    ("M-212", 2888, 2910, "F3", "STUCK_PIPE", "MEDIUM", "Overpull increased during a short trip near the F3 lower contact.", "Tight-hole response after extended drilling without a sweep.", "Circulated and reamed the interval before resuming the trip.", "M-212", 23),
    ("M-216", 3330, 3356, "F4", "KICK_PRESSURE", "LOW", "A flow check was recorded after a pressure fluctuation.", "Transient surface reading; no sustained flow documented.", "Confirmed static conditions and recorded the check result.", "M-216", 6),
    ("M-219", 2390, 2416, "F2", "CEMENTING", "MEDIUM", "Cement returns fell below the planned displacement volume.", "Permeable interval affected the slurry return balance.", "Completed a top-up and documented the final cement volume.", "M-219", 27),
    ("T-301", 2818, 2840, "F3", "MUD_LOSS", "LOW", "Minor return reduction noted near the top of the lower F3 sandstone.", "Small, stable loss with no reported pressure anomaly.", "Observed returns and held the mud program steady.", "T-301", 21),
    ("T-304", 3094, 3120, "F4", "TORQUE_DRAG", "MEDIUM", "Rotary torque rose during the F4 directional section.", "Higher side force was recorded after a trajectory change.", "Reamed the interval and compared pickup/slack-off weights.", "T-304", 12),
]

# Curated development-only context for the active F3 comparison scenario.
# These values are illustrative and must never be presented as OIL field data.
RESERVOIR_SPECS = [
    ("A-101", "F3", 2420, 2960, "Lower sandstone with interbedded shale", 18.4, 96.0, "No direct pore-pressure survey; compare nearby pressure-event records."),
    ("W-014", "F3", 2420, 2960, "F3 sandstone; loss interval at 2,830–2,860 m", 17.8, 88.0, "Development pressure context only; no measured PPFG curve."),
    ("W-021", "F3", 2420, 2960, "F3 sandstone with a permeable lower bed", 19.1, 112.0, "Development pressure context only; no measured PPFG curve."),
    ("W-031", "F3", 2420, 2960, "F3 sandstone near the lower contact", 20.0, 128.0, "Development pressure context only; no measured PPFG curve."),
]

MUD_PROGRAM_SPECS = [
    ("A-101", "F3", 2420, 2960, "Water-based mud", 1.14, 1.18),
    ("W-014", "F3", 2420, 2960, "Water-based mud", 1.13, 1.17),
    ("W-021", "F3", 2420, 2960, "Water-based mud", 1.14, 1.18),
    ("W-031", "F3", 2420, 2960, "Water-based mud", 1.15, 1.19),
]

CASING_PROGRAM_SPECS = [
    ("A-101", '13 3/8 in', 620, "Surface casing"),
    ("A-101", '9 5/8 in', 2420, "Intermediate casing"),
    ("W-014", '9 5/8 in', 2420, "Intermediate casing"),
    ("W-021", '9 5/8 in', 2420, "Intermediate casing"),
    ("W-031", '9 5/8 in', 2420, "Intermediate casing"),
]


def _location(field, east_km, north_km):
    center_lat, center_lon = FIELD_CENTERS[field]
    latitude = center_lat + north_km / 111.32
    longitude = center_lon + east_km / (111.32 * math.cos(math.radians(center_lat)))
    return round(latitude, 6), round(longitude, 6)


def build_development_data():
    wells = []
    surveys = []
    for field, entries in WELL_GROUPS.items():
        for code, east, north, formation, status, total_depth, current_depth in entries:
            latitude, longitude = _location(field, east, north)
            wells.append({
                "well_code": code,
                "name": field + " " + code,
                "field": field,
                "latitude": latitude,
                "longitude": longitude,
                "status": status,
                "spud_date": "2024-03-18" if code == "A-101" else "2022-08-12",
                "total_depth": total_depth,
                "current_depth": current_depth,
                "formation": formation,
            })
            surveys.extend([
                {"well_code": code, "measured_depth": 0, "tvd": 0, "inclination": 0.0, "azimuth": 0.0},
                {"well_code": code, "measured_depth": round(total_depth * 0.50), "tvd": round(total_depth * 0.498), "inclination": 4.2, "azimuth": 78.0},
                {"well_code": code, "measured_depth": total_depth, "tvd": round(total_depth * 0.992), "inclination": 8.6, "azimuth": 82.0},
            ])

    events = []
    for index, spec in enumerate(EVENT_SPECS, start=1):
        code, start, end, formation, event_type, severity, description, cause, mitigation, source_suffix, page = spec
        events.append({
            "event_id": "DEV-E" + str(index).zfill(3),
            "well_code": code,
            "depth_start": start,
            "depth_end": end,
            "formation": formation,
            "event_type": event_type,
            "severity": severity,
            "description": description,
            "cause": cause,
            "mitigation": mitigation,
            "source_document": "DEV-DDR-" + source_suffix + "-23",
            "source_page": page,
        })

    parameters = [
        {"well_code": "A-101", "timestamp": "2026-10-01T03:50:00Z", "depth": 2820, "rop": 19.4, "wob": 13.1, "rpm": 118, "torque": 11.9, "standpipe_pressure": 173, "mud_weight": 1.16, "flow_rate": 1.82, "pit_volume": 38.4},
        {"well_code": "A-101", "timestamp": "2026-10-01T04:01:00Z", "depth": 2830, "rop": 18.8, "wob": 13.4, "rpm": 116, "torque": 12.3, "standpipe_pressure": 175, "mud_weight": 1.16, "flow_rate": 1.82, "pit_volume": 38.4},
        {"well_code": "A-101", "timestamp": "2026-10-01T04:12:00Z", "depth": 2840, "rop": 18.2, "wob": 13.6, "rpm": 114, "torque": 12.8, "standpipe_pressure": 176, "mud_weight": 1.16, "flow_rate": 1.81, "pit_volume": 38.3},
        {"well_code": "W-014", "timestamp": "2023-08-06T14:10:00+05:30", "depth": 2845, "rop": 12.1, "wob": 14.0, "rpm": 105, "torque": 14.1, "standpipe_pressure": 181, "mud_weight": 1.15, "flow_rate": 1.72, "pit_volume": 34.2},
        {"well_code": "W-021", "timestamp": "2023-11-19T08:20:00+05:30", "depth": 2860, "rop": 11.6, "wob": 13.7, "rpm": 102, "torque": 13.8, "standpipe_pressure": 184, "mud_weight": 1.16, "flow_rate": 1.70, "pit_volume": 31.8},
        {"well_code": "W-031", "timestamp": "2023-12-02T17:35:00+05:30", "depth": 2875, "rop": 9.8, "wob": 14.2, "rpm": 99, "torque": 14.8, "standpipe_pressure": 188, "mud_weight": 1.17, "flow_rate": 1.62, "pit_volume": 29.6},
    ]
    return {
        "formations": FORMATIONS,
        "wells": wells,
        "formation_intervals": [
            {"formation": item["name"], "top_depth": item["top_depth"], "bottom_depth": item["bottom_depth"]}
            for item in FORMATIONS
        ],
        "surveys": surveys,
        "events": events,
        "parameters": parameters,
    }
