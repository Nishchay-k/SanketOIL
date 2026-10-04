"""Send a deterministic development telemetry sequence to the local API."""

import argparse
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def read_latest(base_url, well_code):
    url = base_url.rstrip("/") + "/api/telemetry?well_id=" + quote(well_code)
    with urlopen(url, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    readings = payload.get("readings") or []
    if not readings:
        raise RuntimeError("The API returned no baseline telemetry.")
    return readings[0]


def send_reading(base_url, well_code, reading):
    url = base_url.rstrip("/") + "/api/telemetry"
    body = dict(reading, well_id=well_code)
    request = Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))["reading"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--well-id", default="A-101")
    parser.add_argument("--steps", type=int, default=6, help="Number of readings to send (0 runs until interrupted).")
    parser.add_argument("--interval", type=float, default=4.0, help="Seconds between readings.")
    args = parser.parse_args()
    if args.steps < 0 or args.interval < 0:
        parser.error("--steps and --interval must be non-negative.")
    try:
        current = read_latest(args.base_url, args.well_id)
        step = 0
        while args.steps == 0 or step < args.steps:
            step += 1
            depth = min(8000, float(current["depth"]) + 10)
            loss_step = step % 3 == 2
            current = send_reading(args.base_url, args.well_id, {
                "depth": depth,
                "formation": "F3" if depth < 2960 else "F4",
                "rop": 17.6 if not loss_step else 15.2,
                "wob": 13.8,
                "rpm": 112,
                "torque": 13.1,
                "standpipe_pressure": 177 if not loss_step else 179,
                "mud_weight": float(current["mud_weight"]),
                "flow_rate": 1.78 if not loss_step else 1.48,
                "pit_volume": max(0, float(current["pit_volume"]) - (0.9 if loss_step else 0.0)),
            })
            print(args.well_id + " · " + format(depth, ".0f") + " m · pit " + format(current["pit_volume"], ".1f") + " m³")
            if args.steps == 0 or step < args.steps:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nTelemetry simulation stopped.")
    except (HTTPError, URLError, TimeoutError, RuntimeError) as error:
        raise SystemExit("Could not reach the API at " + args.base_url + ": " + str(error))


if __name__ == "__main__":
    main()
