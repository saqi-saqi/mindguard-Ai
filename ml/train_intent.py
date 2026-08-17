"""Train MindGuard's Multi-Turn Intent Classifier with 5-Fold Calibration and Low-Confidence Fallback."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from training_utils import (
    SEED,
    build_tfidf_features,
    file_sha256,
    load_splits,
    multiclass_metrics,
    save_artifact,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MULTITURN_DATA = PROJECT_ROOT / "dataset" / "processed" / "intent_multiturn"
DEFAULT_DATA = MULTITURN_DATA if MULTITURN_DATA.exists() else (PROJECT_ROOT / "dataset" / "processed" / "intent")
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "intent_classifier.joblib"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--known-coverage",
        type=float,
        default=0.95,
        help="Fraction of correctly classified validation examples retained above the confidence threshold.",
    )
    return parser.parse_args()


def select_confidence_threshold(
    y_true: pd.Series,
    prediction: np.ndarray,
    confidence: np.ndarray,
    known_coverage: float,
) -> float:
    correct_confidence = confidence[prediction == y_true.to_numpy()]
    if correct_confidence.size == 0:
        return 0.5
    threshold = float(np.quantile(correct_confidence, 1.0 - known_coverage))
    return float(np.clip(threshold, 0.20, 0.80))


def fallback_metrics(
    y_true: pd.Series, prediction: np.ndarray, confidence: np.ndarray, threshold: float
) -> dict:
    accepted = confidence >= threshold
    correct = prediction == y_true.to_numpy()
    return {
        "threshold": threshold,
        "coverage": float(accepted.mean()),
        "abstention_rate": float((~accepted).mean()),
        "accepted_accuracy": float(correct[accepted].mean()) if accepted.any() else 0.0,
        "correct_and_accepted_rate": float((correct & accepted).mean()),
        "accepted_examples": int(accepted.sum()),
        "fallback_examples": int((~accepted).sum()),
    }


def main() -> None:
    args = parse_args()
    if not 0 < args.known_coverage <= 1:
        raise ValueError("--known-coverage must be greater than 0 and at most 1")

    frames, dataset_metadata = load_splits(args.data_dir, "intent")

    # Base Logistic Regression with balanced class weights
    base_clf = LogisticRegression(
        C=2.5,
        class_weight="balanced",
        max_iter=3_000,
        solver="lbfgs",
        random_state=SEED,
    )

    # 5-fold Stratified Platt Scaling (Calibrated probabilities across all classes)
    calibrated_classifier = CalibratedClassifierCV(
        estimator=base_clf,
        method="sigmoid",
        cv=5,
    )

    pipeline = Pipeline([
        ("features", build_tfidf_features(word_features=45_000, character_features=45_000)),
        ("classifier", calibrated_classifier),
    ])

    print("Training 5-fold calibrated Multi-Turn Intent Classifier...")
    pipeline.fit(frames["train"]["text"], frames["train"]["intent"])
    labels = list(pipeline.named_steps["classifier"].classes_)

    # Validation evaluation
    validation_probabilities = pipeline.predict_proba(frames["validation"]["text"])
    validation_indices = validation_probabilities.argmax(axis=1)
    validation_prediction = np.asarray(labels)[validation_indices]
    validation_confidence = validation_probabilities.max(axis=1)
    confidence_threshold = select_confidence_threshold(
        frames["validation"]["intent"],
        validation_prediction,
        validation_confidence,
        args.known_coverage,
    )
    validation_metrics = multiclass_metrics(
        frames["validation"]["intent"], validation_prediction, labels
    )
    validation_fallback = fallback_metrics(
        frames["validation"]["intent"],
        validation_prediction,
        validation_confidence,
        confidence_threshold,
    )

    # Test evaluation
    test_probabilities = pipeline.predict_proba(frames["test"]["text"])
    test_indices = test_probabilities.argmax(axis=1)
    test_prediction = np.asarray(labels)[test_indices]
    test_confidence = test_probabilities.max(axis=1)
    test_metrics = multiclass_metrics(frames["test"]["intent"], test_prediction, labels)
    test_fallback = fallback_metrics(
        frames["test"]["intent"], test_prediction, test_confidence, confidence_threshold
    )

    # Out of scope holdout evaluation
    out_of_scope_path = args.data_dir.resolve() / "out_of_scope_examples.csv"
    out_of_scope_evaluation = None
    if out_of_scope_path.exists():
        out_of_scope = pd.read_csv(out_of_scope_path).dropna(subset=["text"])
        unknown_probabilities = pipeline.predict_proba(out_of_scope["text"].astype(str))
        unknown_confidence = unknown_probabilities.max(axis=1)
        out_of_scope_evaluation = {
            "file": str(out_of_scope_path),
            "file_sha256": file_sha256(out_of_scope_path),
            "examples": len(out_of_scope),
            "rejected_as_fallback": int((unknown_confidence < confidence_threshold).sum()),
            "rejection_rate": float((unknown_confidence < confidence_threshold).mean()),
            "warning": "Small diagnostic set; not used to select the threshold.",
        }

    created_at = datetime.now(timezone.utc).isoformat()
    artifact = {
        "task": "intent_classification",
        "pipeline": pipeline,
        "classes": labels,
        "fallback_label": "fallback",
        "confidence_threshold": confidence_threshold,
        "created_at_utc": created_at,
        "dataset": dataset_metadata,
    }
    metrics_document = {
        "task": artifact["task"],
        "created_at_utc": created_at,
        "dataset": dataset_metadata,
        "known_validation_coverage_target": args.known_coverage,
        "selected_confidence_threshold": confidence_threshold,
        "validation": validation_metrics,
        "validation_with_fallback": validation_fallback,
        "held_out_test": test_metrics,
        "held_out_test_with_fallback": test_fallback,
        "out_of_scope_diagnostic": out_of_scope_evaluation,
    }
    metrics_path = save_artifact(args.output, artifact, metrics_document)

    # Synchronize artifact to workspace root artifacts directory
    workspace_root = PROJECT_ROOT.parent
    root_artifacts = workspace_root / "artifacts"
    if root_artifacts.exists():
        root_joblib = root_artifacts / args.output.name
        root_metrics = root_artifacts / metrics_path.name
        shutil.copy2(args.output, root_joblib)
        shutil.copy2(metrics_path, root_metrics)
        print(f"Synchronized artifact to root: {root_joblib}")

    print(
        json.dumps(
            {
                "classes": len(labels),
                "confidence_threshold": round(confidence_threshold, 4),
                "validation_accuracy": round(validation_metrics["accuracy"], 4),
                "validation_macro_f1": round(validation_metrics["macro_f1"], 4),
                "validation_weighted_f1": round(validation_metrics["weighted_f1"], 4),
                "test_accuracy": round(test_metrics["accuracy"], 4),
                "test_macro_f1": round(test_metrics["macro_f1"], 4),
                "test_weighted_f1": round(test_metrics["weighted_f1"], 4),
                "test_coverage": round(test_fallback["coverage"], 4),
                "model": str(args.output.resolve()),
                "metrics": str(metrics_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
