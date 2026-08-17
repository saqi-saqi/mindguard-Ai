"""Shared utilities for the three MindGuard text-classification trainers."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import FeatureUnion, Pipeline


SEED = 42


def normalized_key(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_splits(data_dir: Path, label_column: str) -> tuple[dict[str, pd.DataFrame], dict]:
    data_dir = data_dir.resolve()
    frames: dict[str, pd.DataFrame] = {}
    hashes = {}
    for split in ("train", "validation", "test"):
        path = data_dir / f"{split}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing {split} file: {path}")
        frame = pd.read_csv(path)
        required = {"text", label_column}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"{path.name} is missing columns: {sorted(missing)}")
        frame = frame[["text", label_column]].dropna().copy()
        frame["text"] = frame["text"].astype(str).str.strip()
        frame[label_column] = frame[label_column].astype(str).str.strip()
        frame = frame[frame["text"].ne("") & frame[label_column].ne("")].reset_index(drop=True)
        if frame.empty:
            raise ValueError(f"{path.name} contains no usable rows")
        frames[split] = frame
        hashes[path.name] = file_sha256(path)

    keys = {
        split: set(frame["text"].map(normalized_key)) for split, frame in frames.items()
    }
    overlaps = {
        "train_validation": len(keys["train"] & keys["validation"]),
        "train_test": len(keys["train"] & keys["test"]),
        "validation_test": len(keys["validation"] & keys["test"]),
    }
    if any(overlaps.values()):
        raise ValueError(f"Normalized text overlaps across splits: {overlaps}")

    metadata = {
        "directory": str(data_dir),
        "file_sha256": hashes,
        "rows": {split: len(frame) for split, frame in frames.items()},
        "labels": sorted(
            set().union(*(set(frame[label_column].unique()) for frame in frames.values()))
        ),
        "cross_split_overlap": overlaps,
    }
    return frames, metadata


def build_tfidf_features(
    word_features: int = 50_000,
    character_features: int = 50_000,
) -> FeatureUnion:
    return FeatureUnion(
        [
            (
                "word",
                TfidfVectorizer(
                    ngram_range=(1, 2),
                    min_df=2,
                    max_df=0.98,
                    max_features=word_features,
                    strip_accents="unicode",
                    sublinear_tf=True,
                    dtype=np.float32,
                ),
            ),
            (
                "character",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    min_df=2,
                    max_features=character_features,
                    sublinear_tf=True,
                    dtype=np.float32,
                ),
            ),
        ]
    )


def build_pipeline(classifier: Any, word_features: int = 50_000, character_features: int = 50_000) -> Pipeline:
    return Pipeline(
        [
            ("features", build_tfidf_features(word_features, character_features)),
            ("classifier", classifier),
        ]
    )


def multiclass_metrics(y_true: pd.Series, y_pred: np.ndarray, labels: list[str]) -> dict:
    matrix = confusion_matrix(y_true, y_pred, labels=labels)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_precision": float(
            precision_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
        ),
        "macro_recall": float(
            recall_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
        ),
        "macro_f1": float(
            f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
        ),
        "weighted_f1": float(
            f1_score(y_true, y_pred, labels=labels, average="weighted", zero_division=0)
        ),
        "confusion_matrix": {
            "labels": labels,
            "values": matrix.astype(int).tolist(),
        },
        "classification_report": classification_report(
            y_true,
            y_pred,
            labels=labels,
            output_dict=True,
            zero_division=0,
        ),
    }


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def save_artifact(output: Path, artifact: dict, metrics_document: dict) -> Path:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, output)
    metrics_path = output.with_suffix(".metrics.json")
    metrics_path.write_text(
        json.dumps(to_jsonable(metrics_document), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return metrics_path
