"""Generate simulated multi-turn conversation context dataset for intent classification."""

from __future__ import annotations

import argparse
import random
from pathlib import Path
import pandas as pd

from training_utils import SEED

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DATA_DIR = PROJECT_ROOT / "dataset" / "processed" / "intent"
OUTPUT_DATA_DIR = PROJECT_ROOT / "dataset" / "processed" / "intent_multiturn"

INTENT_CONTEXT_PROMPTS = {
    "meditation_interest": [
        "Would you like to try a 2-minute breathing exercise together?",
        "Should we do a guided mindfulness practice to help you center yourself?",
        "Would you be open to trying a short body scan meditation?",
        "I can walk you through a quick relaxation routine if you'd like.",
    ],
    "sleep_problem": [
        "How has your sleep been over the past few nights?",
        "Are you able to fall asleep and stay asleep comfortably?",
        "Have you been having trouble getting quality rest lately?",
        "Tell me more about how your nights have been going.",
    ],
    "anxiety_or_fear": [
        "What has been making you feel most uneasy today?",
        "Can you share what specifically is triggering that anxious feeling?",
        "How is your body responding when you start feeling panicked?",
        "Take a slow breath. What is worrying you right now?",
    ],
    "sadness_or_low_self_worth": [
        "I'm here with you. How have your emotions been feeling today?",
        "It's completely safe to share what's weighing on your mind.",
        "What thoughts have been bringing you down recently?",
        "Tell me what has been making you feel this way.",
    ],
    "social_loneliness": [
        "Have you been able to connect with any friends or family lately?",
        "Do you have someone in your life you feel safe opening up to?",
        "How is your social environment feeling at the moment?",
    ],
    "goodbye": [
        "Is there anything else you'd like to explore before we wrap up?",
        "I'm glad we could chat today. Do you need anything else?",
        "Take good care of yourself today. Any other questions before you go?",
    ],
    "positive_feedback": [
        "I hope that technique gave you a bit of breathing room.",
        "Remember to celebrate taking time for your well-being today.",
        "I'm glad to be here supporting you on this journey.",
    ],
    "negative_feedback": [
        "I want to make sure I am truly understanding your needs.",
        "Let me know if this advice resonates or if we should try a different approach.",
        "I'm listening carefully. How does that suggestion sound to you?",
    ],
    "help_request": [
        "How can I best support you in this moment?",
        "What kind of guidance or resources are you looking for right now?",
        "I'm ready to assist. What is the main challenge you are facing?",
    ],
    "greeting_or_introduction": [
        "Welcome to MindGuard! How are you doing today?",
        "Hi! I'm here whenever you want to check in or talk.",
        "Good to see you. How is your day starting out?",
    ],
    "stress_or_problem": [
        "It sounds like there's a lot on your plate. What happened?",
        "Can you tell me more about what is causing this stress?",
        "What feels like the biggest hurdle you are dealing with right now?",
    ],
    "positive_mood": [
        "How have things been going for you lately?",
        "It sounds like something good happened. What's the update?",
        "Tell me about what brought a smile to your face today.",
    ],
    "bot_information": [
        "Feel free to ask anything about how MindGuard works or who created it.",
        "I'm your AI mental wellness companion. What would you like to know?",
    ],
    "mental_health_information": [
        "What mental health topic would you like to learn more about?",
        "I can share evidence-based information on symptoms, therapies, and coping tools.",
    ],
    "humor_request": [
        "Would you like a lighthearted joke or fun fact to brighten your moment?",
        "Need a quick laugh to break up the day?",
    ],
    "reluctance_or_change_topic": [
        "We can talk about whatever you feel comfortable with.",
        "Would you like to try talking about something else or take a pause?",
    ],
    "casual_conversation": [
        "What's on your mind today?",
        "Feel free to share whatever you're thinking about.",
    ],
}

GENERAL_NEUTRAL_PROMPTS = [
    "How has your day been going so far?",
    "I'm here whenever you'd like to talk.",
    "Take your time. What's on your mind?",
    "Can you tell me more about that?",
]


def generate_context_prefix(intent: str, rng: random.Random) -> str:
    pool = INTENT_CONTEXT_PROMPTS.get(intent, GENERAL_NEUTRAL_PROMPTS)
    num_turns = rng.choice([1, 2])
    if num_turns == 1 or len(pool) == 1:
        return rng.choice(pool)
    sampled = rng.sample(pool, k=min(num_turns, len(pool)))
    return " \n ".join(sampled)


def augment_split_with_multiturn(df: pd.DataFrame, is_train: bool, rng: random.Random) -> pd.DataFrame:
    augmented_rows = []

    for _, row in df.iterrows():
        text = str(row["text"]).strip()
        intent = str(row["intent"]).strip()

        # 50% chance of adding preceding context turn
        if rng.random() < 0.50:
            prefix = generate_context_prefix(intent, rng)
            combined_text = f"{prefix} \n {text}"
        else:
            combined_text = text

        augmented_rows.append({"text": combined_text, "intent": intent})

    if is_train:
        synthetic_train_turns = [
            ("Would you like to try a guided breathing exercise?", "yes", "meditation_interest"),
            ("Would you like to try a guided breathing exercise?", "sure let's do it", "meditation_interest"),
            ("Should we do a 2-minute meditation?", "yeah please", "meditation_interest"),
            ("How did you sleep last night?", "not at all", "sleep_problem"),
            ("How did you sleep last night?", "it's getting worse", "sleep_problem"),
            ("Are you able to fall asleep easily?", "barely an hour", "sleep_problem"),
            ("What is causing you anxiety today?", "my exam tomorrow", "anxiety_or_fear"),
            ("What is causing you anxiety today?", "everything is overwhelming", "anxiety_or_fear"),
            ("Is there anything else I can help you with?", "no that's all, bye", "goodbye"),
            ("Is there anything else I can help you with?", "have to go now", "goodbye"),
            ("I hope that breathing exercise helped you.", "thank you so much", "positive_feedback"),
            ("I hope that breathing exercise helped you.", "that really helped a lot", "positive_feedback"),
            ("How can I best support you in this moment?", "what should I do?", "help_request"),
            ("How can I best support you in this moment?", "I need some advice", "help_request"),
        ]
        for ctx, resp, syn_intent in synthetic_train_turns:
            augmented_rows.append({"text": f"{ctx} \n {resp}", "intent": syn_intent})

    return pd.DataFrame(augmented_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=INPUT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DATA_DIR)
    args = parser.parse_args()

    rng = random.Random(SEED)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating multi-turn simulated intent dataset in {output_dir}...")

    for split in ("train", "validation", "test"):
        input_path = args.input_dir / f"{split}.csv"
        if not input_path.exists():
            raise FileNotFoundError(f"Missing input split: {input_path}")

        df = pd.read_csv(input_path)
        is_train = (split == "train")
        augmented_df = augment_split_with_multiturn(df, is_train, rng)

        output_path = output_dir / f"{split}.csv"
        augmented_df.to_csv(output_path, index=False, encoding="utf-8")
        print(f"Saved {split}.csv ({len(augmented_df)} rows)")

    # Copy out_of_scope_examples.csv and taxonomy.csv if present
    for extra_file in ("out_of_scope_examples.csv", "taxonomy.csv"):
        src = args.input_dir / extra_file
        if src.exists():
            dst = output_dir / extra_file
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    print("Multi-turn intent dataset generation complete!")


if __name__ == "__main__":
    main()
