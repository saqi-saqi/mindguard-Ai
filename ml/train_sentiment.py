"""Train MindGuard's positive/neutral/negative sentiment classifier."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sklearn.linear_model import SGDClassifier

from training_utils import SEED, build_pipeline, load_splits, multiclass_metrics, save_artifact


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = PROJECT_ROOT / "dataset" / "processed" / "sentiment"
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "sentiment_classifier.joblib"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frames, dataset_metadata = load_splits(args.data_dir, "label")
    classifier = SGDClassifier(
        loss="log_loss",
        penalty="l2",
        alpha=1e-5,
        class_weight="balanced",
        max_iter=2_000,
        tol=1e-4,
        average=True,
        random_state=SEED,
    )
    pipeline = build_pipeline(classifier)
    print("Training sentiment classifier...")
    pipeline.fit(frames["train"]["text"], frames["train"]["label"])
    labels = list(pipeline.named_steps["classifier"].classes_)

    validation_prediction = pipeline.predict(frames["validation"]["text"])
    validation_metrics = multiclass_metrics(
        frames["validation"]["label"], validation_prediction, labels
    )
    test_prediction = pipeline.predict(frames["test"]["text"])
    test_metrics = multiclass_metrics(frames["test"]["label"], test_prediction, labels)

    created_at = datetime.now(timezone.utc).isoformat()
    artifact = {
        "task": "sentiment_classification",
        "pipeline": pipeline,
        "classes": labels,
        "created_at_utc": created_at,
        "dataset": dataset_metadata,
    }
    metrics_document = {
        "task": artifact["task"],
        "created_at_utc": created_at,
        "dataset": dataset_metadata,
        "validation": validation_metrics,
        "held_out_test": test_metrics,
    }
    metrics_path = save_artifact(args.output, artifact, metrics_document)
    print(
        json.dumps(
            {
                "validation_macro_f1": round(validation_metrics["macro_f1"], 4),
                "test_macro_f1": round(test_metrics["macro_f1"], 4),
                "test_accuracy": round(test_metrics["accuracy"], 4),
                "model": str(args.output.resolve()),
                "metrics": str(metrics_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
