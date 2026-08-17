"""Train MindGuard's binary crisis-risk classifier with 5-fold CV thresholding & probability calibration."""

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
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline

from training_utils import SEED, build_tfidf_features, load_splits, save_artifact


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = PROJECT_ROOT / "dataset" / "processed" / "crisis"
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "crisis_detector.joblib"
ROOT_ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "artifacts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target-recall", type=float, default=0.95)
    return parser.parse_args()


def choose_threshold(y_true, probabilities: np.ndarray, target_recall: float) -> float:
    precision, recall, thresholds = precision_recall_curve(
        y_true, probabilities, pos_label="suicide"
    )
    eligible = np.flatnonzero(recall[:-1] >= target_recall)
    if eligible.size == 0:
        return 0.5
    best_precision = precision[:-1][eligible].max()
    finalists = eligible[np.isclose(precision[:-1][eligible], best_precision)]
    return float(thresholds[finalists[-1]])


def perform_5fold_cv_threshold_selection(
    train_text: pd.Series, train_label: pd.Series, target_recall: float
) -> tuple[float, dict]:
    """Perform 5-fold Stratified CV on training data to compute robust, non-overfit threshold stats."""
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    fold_thresholds = []

    for fold, (train_idx, val_idx) in enumerate(skf.split(train_text, train_label)):
        X_tr, y_tr = train_text.iloc[train_idx], train_label.iloc[train_idx]
        X_va, y_va = train_text.iloc[val_idx], train_label.iloc[val_idx]

        base_lr = LogisticRegression(
            C=2.0,
            class_weight="balanced",
            max_iter=1_000,
            random_state=SEED,
            solver="liblinear",
        )
        fold_pipeline = Pipeline([
            ("features", build_tfidf_features()),
            ("classifier", CalibratedClassifierCV(estimator=base_lr, method="sigmoid", cv=3))
        ])
        fold_pipeline.fit(X_tr, y_tr)

        classes = list(fold_pipeline.named_steps["classifier"].classes_)
        pos_idx = classes.index("suicide")
        val_probs = fold_pipeline.predict_proba(X_va)[:, pos_idx]

        tau = choose_threshold(y_va, val_probs, target_recall)
        fold_thresholds.append(tau)

    fold_thresholds_arr = np.array(fold_thresholds)
    cv_stats = {
        "fold_thresholds": fold_thresholds_arr.tolist(),
        "mean_threshold": float(np.mean(fold_thresholds_arr)),
        "std_threshold": float(np.std(fold_thresholds_arr)),
        "min_threshold": float(np.min(fold_thresholds_arr)),
        "max_threshold": float(np.max(fold_thresholds_arr)),
        "p95_conservative_threshold": float(np.percentile(fold_thresholds_arr, 95)),
    }
    return cv_stats["mean_threshold"], cv_stats


def evaluate(y_true, probabilities: np.ndarray, threshold: float) -> dict:
    predicted = np.where(probabilities >= threshold, "suicide", "non_suicide")
    tn, fp, fn, tp = confusion_matrix(
        y_true, predicted, labels=["non_suicide", "suicide"]
    ).ravel()
    binary_true = (y_true.to_numpy() == "suicide").astype(int)
    
    brier = float(brier_score_loss(binary_true, probabilities))

    return {
        "threshold": threshold,
        "precision": float(
            precision_score(y_true, predicted, pos_label="suicide", zero_division=0)
        ),
        "recall": float(recall_score(y_true, predicted, pos_label="suicide", zero_division=0)),
        "f1": float(f1_score(y_true, predicted, pos_label="suicide", zero_division=0)),
        "roc_auc": float(roc_auc_score(binary_true, probabilities)),
        "average_precision": float(average_precision_score(binary_true, probabilities)),
        "brier_score": brier,
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
    }


def main() -> None:
    args = parse_args()
    if not 0 < args.target_recall <= 1:
        raise ValueError("--target-recall must be greater than 0 and at most 1")

    frames, dataset_metadata = load_splits(args.data_dir, "label")

    print("Executing 5-fold cross-validation threshold selection...")
    cv_mean_threshold, cv_stats = perform_5fold_cv_threshold_selection(
        frames["train"]["text"], frames["train"]["label"], args.target_recall
    )

    base_lr = LogisticRegression(
        C=2.0,
        class_weight="balanced",
        max_iter=1_000,
        random_state=SEED,
        solver="liblinear",
    )
    # Calibrated Classifier Pipeline
    pipeline = Pipeline([
        ("features", build_tfidf_features()),
        ("classifier", CalibratedClassifierCV(estimator=base_lr, method="sigmoid", cv=5))
    ])

    print("Training calibrated crisis classifier on full training split...")
    pipeline.fit(frames["train"]["text"], frames["train"]["label"])

    classes = list(pipeline.named_steps["classifier"].classes_)
    positive_index = classes.index("suicide")

    validation_probabilities = pipeline.predict_proba(frames["validation"]["text"])[
        :, positive_index
    ]
    # Evaluate using the 5-fold CV calibrated threshold
    threshold = cv_mean_threshold
    validation_metrics = evaluate(
        frames["validation"]["label"], validation_probabilities, threshold
    )

    test_probabilities = pipeline.predict_proba(frames["test"]["text"])[
        :, positive_index
    ]
    test_metrics = evaluate(frames["test"]["label"], test_probabilities, threshold)
    created_at = datetime.now(timezone.utc).isoformat()

    artifact = {
        "task": "crisis_detection",
        "pipeline": pipeline,
        "classes": classes,
        "positive_label": "suicide",
        "threshold": threshold,
        "created_at_utc": created_at,
        "dataset": dataset_metadata,
        "cv_threshold_stats": cv_stats,
        "safety_note": "Calibrated model; research prototype only; never use as the sole crisis safety control.",
    }
    metrics_document = {
        "task": artifact["task"],
        "created_at_utc": created_at,
        "dataset": dataset_metadata,
        "target_validation_recall": args.target_recall,
        "selected_threshold": threshold,
        "cv_threshold_stats": cv_stats,
        "validation": validation_metrics,
        "held_out_test": test_metrics,
    }
    metrics_path = save_artifact(args.output, artifact, metrics_document)

    # Sync artifact to root artifacts folder if it exists
    if ROOT_ARTIFACTS_DIR.exists():
        shutil.copy2(args.output, ROOT_ARTIFACTS_DIR / args.output.name)
        shutil.copy2(metrics_path, ROOT_ARTIFACTS_DIR / metrics_path.name)
        print(f"Synced artifacts to root directory: {ROOT_ARTIFACTS_DIR}")

    print(
        json.dumps(
            {
                "threshold": round(threshold, 4),
                "cv_threshold_stats": cv_stats,
                "validation_recall": round(validation_metrics["recall"], 4),
                "test_recall": round(test_metrics["recall"], 4),
                "test_precision": round(test_metrics["precision"], 4),
                "test_f1": round(test_metrics["f1"], 4),
                "test_pr_auc": round(test_metrics["average_precision"], 4),
                "test_brier_score": round(test_metrics["brier_score"], 4),
                "test_confusion_matrix": test_metrics["confusion_matrix"],
                "model": str(args.output.resolve()),
                "metrics": str(metrics_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

