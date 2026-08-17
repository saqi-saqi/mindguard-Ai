"""Generate simulated multi-turn conversation context dataset for crisis classification."""

from __future__ import annotations

import argparse
import random
from pathlib import Path
import pandas as pd

from training_utils import SEED, file_sha256, normalized_key

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DATA_DIR = PROJECT_ROOT / "dataset" / "processed" / "crisis"
OUTPUT_DATA_DIR = PROJECT_ROOT / "dataset" / "processed" / "crisis_multiturn"

# Realistic conversation turn templates for simulating multi-turn context
NEUTRAL_PREAMBLES = [
    "Hey, how are you doing today?",
    "I'm feeling a bit tired after work.",
    "Can we talk for a minute?",
    "I've been thinking about life lately.",
    "Things have been pretty quiet today.",
    "I'm not sure how to express what I'm feeling.",
    "Do you have a moment to chat?",
    "It's been a long week.",
    "Is there anything else I can help you with today?",
    "Would you like to try a guided meditation exercise?",
    "How has your sleep been over the past few nights?",
    "I hope that suggestion was helpful for you.",
    "Take care and have a wonderful afternoon.",
]

DISTRESS_PREAMBLES = [
    "I've been feeling so overwhelmed lately.",
    "Nothing seems to be going right anymore.",
    "I feel like I'm completely alone in this.",
    "I can't stop thinking about all my problems.",
    "Everything just feels too heavy to carry.",
    "I've tried everything, but nothing helps.",
    "I feel like everyone would be better off without me.",
    "I don't know how much longer I can handle this stress.",
]


def generate_context_prefix(label: str, rng: random.Random) -> str:
    """Generate 1 to 2 preceding conversation turns based on the target label."""
    num_turns = rng.choice([1, 2])
    if label == "suicide":
        # Mix distress and neutral preceding turns for crisis cases
        pool = DISTRESS_PREAMBLES if rng.random() > 0.3 else NEUTRAL_PREAMBLES
    else:
        # Mostly neutral preceding turns for non-crisis cases
        pool = NEUTRAL_PREAMBLES

    selected_turns = rng.sample(pool, k=min(num_turns, len(pool)))
    return " \n ".join(selected_turns)


def augment_split_with_multiturn(df: pd.DataFrame, rng: random.Random) -> pd.DataFrame:
    """Augment 50% of the dataset rows with preceding multi-turn context."""
    augmented_rows = []
    for _, row in df.iterrows():
        text = str(row["text"]).strip()
        label = str(row["label"]).strip()

        # 50% chance to add multi-turn context, 50% keep single-turn
        if rng.random() < 0.5:
            prefix = generate_context_prefix(label, rng)
            combined_text = f"{prefix} \n {text}"
        else:
            combined_text = text

        augmented_rows.append({"text": combined_text, "label": label})

    return pd.DataFrame(augmented_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=INPUT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DATA_DIR)
    args = parser.parse_args()

    rng = random.Random(SEED)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating multi-turn simulated dataset in {output_dir}...")

    for split in ("train", "validation", "test"):
        input_path = args.input_dir / f"{split}.csv"
        if not input_path.exists():
            raise FileNotFoundError(f"Missing input split: {input_path}")

        df = pd.read_csv(input_path)
        augmented_df = augment_split_with_multiturn(df, rng)

        output_path = output_dir / f"{split}.csv"
        augmented_df.to_csv(output_path, index=False, encoding="utf-8")
        print(f"Saved {split}.csv ({len(augmented_df)} rows)")

    print("Multi-turn dataset generation complete!")


if __name__ == "__main__":
    main()
