"""Initialize the configured SANKET database and optional development dataset."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import store


def main():
    store.initialize()
    counts = store.row(
        "SELECT (SELECT COUNT(*) FROM wells) AS wells, "
        "(SELECT COUNT(*) FROM drilling_events) AS events, "
        "(SELECT COUNT(*) FROM surveys) AS surveys"
    )
    print("Development database ready:")
    print("  wells: " + str(counts["wells"]))
    print("  events: " + str(counts["events"]))
    print("  survey points: " + str(counts["surveys"]))
    print("  database type: " + store.engine().dialect.name)


if __name__ == "__main__":
    main()
