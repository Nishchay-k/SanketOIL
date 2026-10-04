"""Report stored model metadata without inventing validation metrics."""

import json

from backend.app import store


def main():
    store.initialize()
    models = store.get_model_versions()
    if not models:
        print("No model metadata is registered.")
        return
    for model in models:
        metrics = json.loads(model.get("metrics_json") or "{}")
        print(model["model_version"] + " · " + model["status"])
        print("  Type: " + model["model_type"])
        print("  Dataset: " + model["training_dataset_version"])
        print("  Note: " + model["note"])
        print("  Metrics: " + (json.dumps(metrics, sort_keys=True) if metrics else "not measured"))


if __name__ == "__main__":
    main()
