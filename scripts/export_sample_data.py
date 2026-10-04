"""Export the bundled development records as CSV for inspection or ingestion demos."""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.sample_data import build_development_data

OUTPUT = ROOT / "data" / "sample"


def write_csv(name, records, fields):
    path = OUTPUT / name
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    print("Wrote " + str(path.relative_to(ROOT)) + " (" + str(len(records)) + " records)")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    data = build_development_data()
    write_csv(
        "wells.csv",
        data["wells"],
        ["well_code", "name", "field", "latitude", "longitude", "status", "spud_date", "total_depth", "current_depth", "formation"],
    )
    write_csv("formations.csv", data["formations"], ["name", "top_depth", "bottom_depth", "description"])
    well_ids = {well["well_code"]: well for well in data["wells"]}
    surveys = [dict(item, field=well_ids[item["well_code"]]["field"]) for item in data["surveys"]]
    write_csv("surveys.csv", surveys, ["well_code", "field", "measured_depth", "tvd", "inclination", "azimuth"])
    write_csv("drilling_events.csv", data["events"], ["event_id", "well_code", "depth_start", "depth_end", "formation", "event_type", "severity", "description", "cause", "mitigation", "source_document", "source_page"])
    write_csv("drilling_parameters.csv", data["parameters"], ["well_code", "timestamp", "depth", "rop", "wob", "rpm", "torque", "standpipe_pressure", "mud_weight", "flow_rate", "pit_volume"])


if __name__ == "__main__":
    main()
