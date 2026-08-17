"""Run a single prediction with the saved MindGuard crisis baseline."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import joblib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = PROJECT_ROOT / "artifacts" / "crisis_detector.joblib"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", help="Message to assess")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifact = joblib.load(args.model)
    normalized = re.sub(r"\s+", " ", args.text).strip().lower()
    classes = list(artifact["pipeline"].named_steps["classifier"].classes_)
    positive_label = artifact.get("positive_label", "suicide")
    positive_index = classes.index(positive_label)
    probability = float(
        artifact["pipeline"].predict_proba([normalized])[0, positive_index]
    )
    threshold = float(artifact["threshold"])
    print(
        json.dumps(
            {
                "crisis_risk": probability >= threshold,
                "risk_probability": round(probability, 6),
                "decision_threshold": round(threshold, 6),
                "warning": "Research/demo output; not a diagnosis.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
