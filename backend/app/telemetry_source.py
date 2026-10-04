"""Canonical telemetry source boundary for development and future rig adapters."""

from datetime import datetime, timezone


class TelemetrySource:
    source_name = "abstract"

    def normalize(self, payload):
        raise NotImplementedError


class DevelopmentTelemetrySource(TelemetrySource):
    source_name = "development"

    def normalize(self, payload):
        values = dict(payload)
        values["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        values["source"] = self.source_name
        return values


class ERTMACAdapter(TelemetrySource):
    """Adapter contract only; no OIL endpoint or credentials are configured."""

    source_name = "ertmac"

    def __init__(self, field_map=None):
        self.field_map = dict(field_map or {})

    def normalize(self, payload):
        if not self.field_map:
            raise RuntimeError("An approved eRTMAC field map and source client are required before this adapter can be used.")
        result = {}
        for canonical, source_field in self.field_map.items():
            if source_field not in payload:
                raise ValueError("Required source field is missing: " + str(source_field))
            result[canonical] = payload[source_field]
        result["source"] = self.source_name
        result["timestamp"] = str(payload.get("timestamp") or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"))
        return result


ACTIVE_TELEMETRY_SOURCE = DevelopmentTelemetrySource()
