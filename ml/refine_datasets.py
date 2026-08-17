"""Build cleaned, reproducible MindGuard datasets from the supplied archives.

The script does not invent examples or approve chatbot responses. It removes
invalid rows, normalizes/de-identifies text, resolves exact duplicate leakage,
consolidates intent labels, creates deterministic splits, and marks every
response as requiring human review.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = PROJECT_ROOT / "dataset"
OUTPUT_ROOT = DATASET_ROOT / "processed"
SEED = 42

URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
REDDIT_USER_RE = re.compile(r"(?i)(?<!\w)(?:/?u/)[A-Z0-9_-]+")
HANDLE_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_]{2,}")
WHITESPACE_RE = re.compile(r"\s+")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = html.unescape(str(value)).replace("\x00", " ")
    text = unicodedata.normalize("NFKC", text)
    text = URL_RE.sub("[URL]", text)
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = REDDIT_USER_RE.sub("[USER]", text)
    text = HANDLE_RE.sub("[USER]", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def duplicate_key(text: str) -> str:
    return WHITESPACE_RE.sub(" ", unicodedata.normalize("NFKC", text).casefold()).strip()


def stable_id(namespace: str, label: str, text: str) -> str:
    payload = f"{namespace}\0{label}\0{duplicate_key(text)}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:20]


def read_zip_member(path: Path, member: str) -> tuple[bytes, str]:
    archive_bytes = path.read_bytes()
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        if member not in archive.namelist():
            raise ValueError(f"{member!r} not found in {path.name}")
        return archive.read(member), sha256_bytes(archive_bytes)


def remove_duplicate_conflicts(
    frame: pd.DataFrame, label_column: str
) -> tuple[pd.DataFrame, dict[str, int]]:
    before = len(frame)
    frame = frame.copy()
    frame["_duplicate_key"] = frame["text"].map(duplicate_key)
    conflicting_keys = set(
        frame.groupby("_duplicate_key")[label_column].nunique().loc[lambda values: values > 1].index
    )
    conflicting_rows = int(frame["_duplicate_key"].isin(conflicting_keys).sum())
    frame = frame[~frame["_duplicate_key"].isin(conflicting_keys)]
    before_deduplication = len(frame)
    frame = frame.drop_duplicates("_duplicate_key", keep="first")
    duplicate_rows = before_deduplication - len(frame)
    frame = frame.drop(columns="_duplicate_key").reset_index(drop=True)
    return frame, {
        "rows_before_duplicate_checks": before,
        "conflicting_rows_removed": conflicting_rows,
        "exact_duplicate_rows_removed": duplicate_rows,
    }


def add_stratified_splits(frame: pd.DataFrame, label_column: str) -> pd.DataFrame:
    train, remainder = train_test_split(
        frame,
        test_size=0.30,
        random_state=SEED,
        stratify=frame[label_column],
    )
    validation, test = train_test_split(
        remainder,
        test_size=0.50,
        random_state=SEED,
        stratify=remainder[label_column],
    )
    result = frame.copy()
    result["split"] = ""
    result.loc[train.index, "split"] = "train"
    result.loc[validation.index, "split"] = "validation"
    result.loc[test.index, "split"] = "test"
    if (result["split"] == "").any():
        raise RuntimeError("At least one row did not receive a split")
    return result


def write_split_files(frame: pd.DataFrame, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    ordered = frame.sort_values("example_id").reset_index(drop=True)
    ordered.to_csv(directory / "all.csv", index=False, encoding="utf-8")
    for split in ("train", "validation", "test"):
        ordered.loc[ordered["split"] == split].to_csv(
            directory / f"{split}.csv", index=False, encoding="utf-8"
        )


def distribution(frame: pd.DataFrame, label_column: str) -> dict:
    return {
        split: {
            str(label): int(count)
            for label, count in subset[label_column].value_counts().sort_index().items()
        }
        for split, subset in frame.groupby("split")
    }


def process_crisis() -> tuple[pd.DataFrame, dict]:
    archive = DATASET_ROOT / "archive (5).zip"
    member = "file1.csv"
    raw, archive_hash = read_zip_member(archive, member)
    source = pd.read_csv(BytesIO(raw))
    input_rows = len(source)

    frame = source[["text", "class"]].copy()
    frame["text"] = frame["text"].map(clean_text)
    frame["label"] = (
        frame["class"]
        .astype(str)
        .str.strip()
        .str.casefold()
        .map({"non-suicide": "non_suicide", "suicide": "suicide"})
    )
    valid = frame["text"].ne("") & frame["label"].notna()
    invalid_rows = int((~valid).sum())
    frame = frame.loc[valid, ["text", "label"]]
    frame, duplicate_stats = remove_duplicate_conflicts(frame, "label")
    frame["example_id"] = [stable_id("crisis", label, text) for text, label in zip(frame.text, frame.label)]
    frame["source"] = f"{archive.name}:{member}"
    frame = add_stratified_splits(frame, "label")
    frame = frame[["example_id", "text", "label", "split", "source"]]
    write_split_files(frame, OUTPUT_ROOT / "crisis")

    stats = {
        "source_archive": archive.name,
        "source_member": member,
        "source_archive_sha256": archive_hash,
        "input_rows": input_rows,
        "invalid_or_empty_rows_removed": invalid_rows,
        **duplicate_stats,
        "output_rows": len(frame),
        "split_distribution": distribution(frame, "label"),
    }
    return frame, stats


def process_sentiment() -> tuple[pd.DataFrame, dict]:
    archive = DATASET_ROOT / "archive (4).zip"
    member = "Suicide Sentiment Data/Pos_Neut_Neg.csv"
    raw, archive_hash = read_zip_member(archive, member)
    source = pd.read_csv(BytesIO(raw))
    input_rows = len(source)

    frame = source[["text", "sentiment"]].copy()
    frame["text"] = frame["text"].map(clean_text)
    frame["label"] = frame["sentiment"].astype(str).str.strip().str.casefold()
    valid_labels = {"positive", "neutral", "negative"}
    valid = frame["text"].ne("") & frame["label"].isin(valid_labels)
    invalid_rows = int((~valid).sum())
    frame = frame.loc[valid, ["text", "label"]]
    frame, duplicate_stats = remove_duplicate_conflicts(frame, "label")
    frame["example_id"] = [
        stable_id("sentiment", label, text) for text, label in zip(frame.text, frame.label)
    ]
    frame["source"] = f"{archive.name}:{member}"
    frame = add_stratified_splits(frame, "label")
    frame = frame[["example_id", "text", "label", "split", "source"]]
    write_split_files(frame, OUTPUT_ROOT / "sentiment")

    stats = {
        "source_archive": archive.name,
        "source_member": member,
        "source_archive_sha256": archive_hash,
        "input_rows": input_rows,
        "invalid_or_empty_rows_removed": invalid_rows,
        **duplicate_stats,
        "output_rows": len(frame),
        "split_distribution": distribution(frame, "label"),
        "warning": "This is general social-media sentiment, not a clinically validated mental-health dataset.",
    }
    return frame, stats


def build_intent_mapping(source_tags: set[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}

    def assign(final_label: str, *tags: str) -> None:
        for tag in tags:
            if tag in mapping:
                raise ValueError(f"Intent tag mapped more than once: {tag}")
            mapping[tag] = final_label

    assign(
        "greeting_or_introduction",
        "greeting",
        "morning",
        "afternoon",
        "evening",
        "night",
        "name",
    )
    assign("goodbye", "goodbye", "done")
    assign("bot_information", "about", "creation", "location", "skill")
    assign("help_request", "ask", "help", "user-advice")
    assign("casual_conversation", "casual", "neutral-response")
    assign("positive_mood", "happy")
    assign("positive_feedback", "thanks", "user-agree", "user-meditation", "pandora-useful")
    assign("negative_feedback", "hate-you", "stupid", "repeat", "wrong", "understand")
    assign("anxiety_or_fear", "anxious", "scared")
    assign("sadness_or_low_self_worth", "sad", "depressed", "worthless", "hate-me")
    assign("stress_or_problem", "stressed", "problem")
    assign("sleep_problem", "sleep")
    assign("grief_or_loss", "death")
    assign("social_loneliness", "friends")
    assign("reluctance_or_change_topic", "not-talking", "no-approach", "something-else")
    assign("meditation_interest", "meditation")
    assign("mental_health_information", "learn-mental-health", "learn-more", "mental-health-fact")
    assign("humor_request", "jokes")
    assign("general_support_topic", "default")
    # These examples are held out for unknown/low-confidence testing instead of
    # training a poorly supported intent class from mostly gibberish.
    assign("__out_of_scope_holdout__", "no-response")
    assign("suicide_crisis", "suicide")
    for tag in sorted(source_tags):
        if tag.startswith("fact-"):
            assign("mental_health_information", tag)

    missing = source_tags.difference(mapping)
    unexpected = set(mapping).difference(source_tags)
    if missing or unexpected:
        raise ValueError(
            f"Intent mapping mismatch; unmapped={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    return mapping


def load_intent_sources() -> tuple[list[dict], list[dict], dict[str, str], list[dict]]:
    specs = [
        ("archive.zip", "intents.json"),
        ("archive (2).zip", "New-data.json"),
        ("archive (3).zip", "KB.json"),
    ]
    items: list[dict] = []
    source_records: list[dict] = []
    archive_hashes: dict[str, str] = {}
    for archive_name, member in specs:
        raw, archive_hash = read_zip_member(DATASET_ROOT / archive_name, member)
        archive_hashes[archive_name] = archive_hash
        document = json.loads(raw.decode("utf-8-sig"))
        source_items = document.get("intents", [])
        source_records.append(
            {"archive": archive_name, "member": member, "intent_records": len(source_items)}
        )
        for item in source_items:
            copied = dict(item)
            copied["_source"] = f"{archive_name}:{member}"
            items.append(copied)
    return items, source_records, archive_hashes, specs


def process_intents() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    items, source_records, archive_hashes, _ = load_intent_sources()
    source_tags = {str(item.get("tag", "")).strip() for item in items}
    mapping = build_intent_mapping(source_tags)

    raw_pattern_rows: list[dict] = []
    raw_response_rows: list[dict] = []
    faq_by_tag: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"questions": set(), "answers": set()}
    )
    for item in items:
        source_tag = str(item.get("tag", "")).strip()
        target_intent = mapping[source_tag]
        response_intent = "fallback" if target_intent == "__out_of_scope_holdout__" else target_intent
        source_name = item["_source"]
        for pattern in item.get("patterns", []):
            text = clean_text(pattern)
            if text:
                raw_pattern_rows.append(
                    {
                        "text": text,
                        "intent": target_intent,
                        "source_tag": source_tag,
                        "source": source_name,
                    }
                )
                if source_tag.startswith("fact-"):
                    faq_by_tag[source_tag]["questions"].add(text)

        responses = item.get("responses", [])
        if isinstance(responses, str):
            responses = [responses]
        extra = item.get("response", [])
        if isinstance(extra, str):
            extra = [extra]
        if not isinstance(extra, list):
            extra = []
        for response in list(responses) + extra:
            text = clean_text(response)
            if text:
                raw_response_rows.append(
                    {
                        "text": text,
                        "intent": response_intent,
                        "source_tag": source_tag,
                        "source": source_name,
                    }
                )
                if source_tag.startswith("fact-"):
                    faq_by_tag[source_tag]["answers"].add(text)

    # Combine repeated examples while preserving their provenance.
    pattern_groups: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"texts": set(), "source_tags": set(), "sources": set()}
    )
    labels_by_text: dict[str, set[str]] = defaultdict(set)
    for row in raw_pattern_rows:
        key = duplicate_key(row["text"])
        labels_by_text[key].add(row["intent"])
        group = pattern_groups[(key, row["intent"])]
        group["texts"].add(row["text"])
        group["source_tags"].add(row["source_tag"])
        group["sources"].add(row["source"])

    conflicting_keys = {key for key, labels in labels_by_text.items() if len(labels) > 1}
    consolidated_patterns = []
    for (key, intent), group in pattern_groups.items():
        if key in conflicting_keys:
            continue
        text = sorted(group["texts"], key=lambda value: (len(value), value.casefold()))[0]
        consolidated_patterns.append(
            {
                "text": text,
                "intent": intent,
                "source_tags": ";".join(sorted(group["source_tags"])),
                "sources": ";".join(sorted(group["sources"])),
            }
        )
    all_patterns = pd.DataFrame(consolidated_patterns)
    out_of_scope = all_patterns.loc[
        all_patterns["intent"] == "__out_of_scope_holdout__"
    ].copy()
    frame = all_patterns.loc[
        all_patterns["intent"] != "__out_of_scope_holdout__"
    ].copy()
    frame["example_id"] = [
        stable_id("intent", intent, text) for text, intent in zip(frame.text, frame.intent)
    ]
    frame = add_stratified_splits(frame, "intent")
    frame = frame[["example_id", "text", "intent", "split", "source_tags", "sources"]]
    write_split_files(frame, OUTPUT_ROOT / "intent")

    out_of_scope["example_id"] = [
        stable_id("intent_out_of_scope", "out_of_scope", text) for text in out_of_scope.text
    ]
    out_of_scope["intended_use"] = "unknown_intent_threshold_test"
    out_of_scope = out_of_scope[
        ["example_id", "text", "intended_use", "source_tags", "sources"]
    ].sort_values("example_id")
    out_of_scope.to_csv(
        OUTPUT_ROOT / "intent" / "out_of_scope_examples.csv", index=False, encoding="utf-8"
    )

    taxonomy_rows = [
        {
            "source_tag": source_tag,
            "refined_intent": (
                "out_of_scope_holdout"
                if refined_intent == "__out_of_scope_holdout__"
                else refined_intent
            ),
            "included_in_intent_training": refined_intent != "__out_of_scope_holdout__",
        }
        for source_tag, refined_intent in sorted(mapping.items())
    ]
    pd.DataFrame(taxonomy_rows).to_csv(
        OUTPUT_ROOT / "intent" / "taxonomy.csv", index=False, encoding="utf-8"
    )

    response_groups: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"texts": set(), "source_tags": set(), "sources": set()}
    )
    for row in raw_response_rows:
        key = duplicate_key(row["text"])
        group = response_groups[(row["intent"], key)]
        group["texts"].add(row["text"])
        group["source_tags"].add(row["source_tag"])
        group["sources"].add(row["source"])
    response_records = []
    for (intent, _), group in response_groups.items():
        text = sorted(group["texts"], key=lambda value: (len(value), value.casefold()))[0]
        response_records.append(
            {
                "response_id": stable_id("response", intent, text),
                "intent": intent,
                "text": text,
                "source_tags": ";".join(sorted(group["source_tags"])),
                "sources": ";".join(sorted(group["sources"])),
                "review_status": "needs_human_review",
            }
        )
    response_frame = pd.DataFrame(response_records).sort_values(["intent", "response_id"])
    response_dir = OUTPUT_ROOT / "responses"
    response_dir.mkdir(parents=True, exist_ok=True)
    response_frame.to_csv(
        response_dir / "response_candidates.csv", index=False, encoding="utf-8"
    )

    faq_records = []
    for tag in sorted(faq_by_tag):
        faq_records.append(
            {
                "faq_id": tag,
                "example_questions": sorted(faq_by_tag[tag]["questions"]),
                "candidate_answers": sorted(faq_by_tag[tag]["answers"]),
                "review_status": "needs_human_review",
            }
        )
    (response_dir / "faq_candidates.json").write_text(
        json.dumps(faq_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    intent_counts = frame["intent"].value_counts().sort_index()
    stats = {
        "sources": source_records,
        "source_archive_sha256": archive_hashes,
        "input_intent_records": len(items),
        "original_unique_tags": len(source_tags),
        "refined_intents": int(frame["intent"].nunique()),
        "input_nonempty_pattern_rows": len(raw_pattern_rows),
        "cross_label_conflicting_texts_removed": len(conflicting_keys),
        "output_unique_patterns": len(frame),
        "out_of_scope_holdout_patterns": len(out_of_scope),
        "intent_counts": {str(label): int(count) for label, count in intent_counts.items()},
        "split_distribution": distribution(frame, "intent"),
        "response_candidates_needing_review": len(response_frame),
        "faq_records_needing_review": len(faq_records),
        "warning": (
            "Intent patterns include highly templated/generated-looking language. "
            "Responses and FAQ answers are candidates only and have not been clinically approved."
        ),
    }
    return frame, response_frame, stats


def validate_outputs(crisis: pd.DataFrame, sentiment: pd.DataFrame, intent: pd.DataFrame) -> dict:
    checks = {}
    for name, frame, label_column in (
        ("crisis", crisis, "label"),
        ("sentiment", sentiment, "label"),
        ("intent", intent, "intent"),
    ):
        duplicate_ids = int(frame["example_id"].duplicated().sum())
        duplicate_text = int(frame["text"].map(duplicate_key).duplicated().sum())
        empty_text = int(frame["text"].eq("").sum())
        split_values = sorted(frame["split"].unique().tolist())
        missing_labels = int(frame[label_column].isna().sum())
        check = {
            "duplicate_example_ids": duplicate_ids,
            "duplicate_normalized_texts": duplicate_text,
            "empty_text_rows": empty_text,
            "missing_labels": missing_labels,
            "splits": split_values,
        }
        checks[name] = check
        if any((duplicate_ids, duplicate_text, empty_text, missing_labels)):
            raise RuntimeError(f"Validation failed for {name}: {check}")
        if split_values != ["test", "train", "validation"]:
            raise RuntimeError(f"Unexpected splits for {name}: {split_values}")
    return checks


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    crisis, crisis_stats = process_crisis()
    sentiment, sentiment_stats = process_sentiment()
    intent, responses, intent_stats = process_intents()
    validation = validate_outputs(crisis, sentiment, intent)

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "random_seed": SEED,
        "split_policy": "70% train, 15% validation, 15% test; stratified by label",
        "text_policy": (
            "Unicode NFKC and whitespace normalization; URLs, emails, Reddit usernames, "
            "and @handles replaced; punctuation, stopwords, negation, and emoji retained."
        ),
        "crisis": crisis_stats,
        "sentiment": sentiment_stats,
        "intent": intent_stats,
        "validation": validation,
        "global_warnings": [
            "These datasets support a nonclinical research prototype, not diagnosis.",
            "The source archives do not include clear provenance/license records; verify licenses before redistribution.",
            "Do not modify final test sets while tuning models.",
            "Human review remains required for response candidates and crisis evaluation examples.",
        ],
    }
    (OUTPUT_ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "output": str(OUTPUT_ROOT),
                "crisis_rows": len(crisis),
                "sentiment_rows": len(sentiment),
                "intent_rows": len(intent),
                "refined_intents": int(intent["intent"].nunique()),
                "response_candidates": len(responses),
                "validation": validation,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
