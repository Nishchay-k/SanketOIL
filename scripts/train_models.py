"""Validate whether this development database can support supervised training.

The current seed data records reported events but has no verified safe-interval
labels. Training on undocumented intervals as negatives would create misleading
performance, so this script refuses to fit a model until those labels exist.
"""

from backend.app import store


def main():
    store.initialize()
    summary = store.row(
        """SELECT COUNT(*) AS events,COUNT(DISTINCT well_id) AS wells
           FROM drilling_events WHERE event_type IN ('MUD_LOSS','STUCK_PIPE','KICK_PRESSURE','OVERPRESSURE','TORQUE_DRAG','CEMENTING')"""
    )
    print("Training status: skipped")
    print("Reason: the development dataset contains " + str(summary["events"]) + " reported events across " + str(summary["wells"]) + " wells, but no verified safe-interval labels.")
    print("No model artifact or performance metric was created. The explainable rules and offset evidence remain the active fallback.")


if __name__ == "__main__":
    main()
