"""Build and evaluate a 500-case synthetic Roman Urdu regression set.

This is a diagnostic stress set, not a clinical benchmark or independent
holdout. Ten surface variants are grouped under each of 50 source skeletons,
so report both case and skeleton-level results. Every case needs review by a
native Roman Urdu speaker before the labels are treated as gold.

Run from the repository root:
    python scripts/eval_roman_urdu_synthetic_500.py
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))

from server.services.crisis_rules import evaluate_crisis_pipeline  # noqa: E402

OUTPUT = ROOT / "tests" / "data" / "roman_urdu_synthetic_eval_500.json"


# These examples are newly authored synthetic prompts. The crisis examples
# cover explicit ideation, intent, preparation, self-harm, and farewell signals.
CRISIS_SKELETONS = [
    ("explicit_ideation", "T1", "Mujhe marna hai"),
    ("explicit_ideation", "T1", "Main mar jana chahta hoon"),
    ("explicit_ideation", "T1", "Main apni jaan lena chahta hoon"),
    ("explicit_ideation", "T1", "Mujhe zinda nahi rehna"),
    ("explicit_ideation", "T1", "Zindagi khatam karna chahta hoon"),
    ("explicit_ideation", "T1", "Main khudkushi karne ka soch raha hoon"),
    ("explicit_ideation", "T1", "Ab mujhse zinda nahi raha jata"),
    ("explicit_ideation", "T1", "Mujhe apne aap ko khatam karna hai"),
    ("explicit_ideation", "T1", "Maine apni zindagi khatam karne ka faisla kar liya hai"),
    ("explicit_ideation", "T1", "I want to khatam my life, ab aur nahi hota"),
    ("preparation_or_means", "T2", "Mere paas khud ko nuqsan pohanchane ka plan hai"),
    ("preparation_or_means", "T2", "Main apne aap ko nuqsan dene ki tayari kar raha hoon"),
    ("preparation_or_means", "T2", "Maine bohat zyada goliyan kha li hain"),
    ("preparation_or_means", "T2", "Main chhat se koodne wala hoon"),
    ("preparation_or_means", "T2", "Main blade se apni kalai kaatne ja raha hoon"),
    ("self_harm", "T2", "Main apni kalai kaat raha hoon"),
    ("self_harm", "T2", "Maine apne aap ko zakhmi kar liya hai"),
    ("self_harm", "T2", "Main khud ko hurt karne wala hoon"),
    ("self_harm", "T2", "Main apne aap ko nuqsan pohancha raha hoon"),
    ("self_harm", "T2", "Main khud ko chot pohanchane ka soch raha hoon"),
    ("farewell_or_goodbye", "T3", "Aaj meri aakhri raat hai"),
    ("farewell_or_goodbye", "T3", "Mere baad sab ko keh dena ke main maafi chahta tha"),
    ("farewell_or_goodbye", "T3", "Yeh mera aakhri paighaam hai, main ja raha hoon"),
    ("farewell_or_goodbye", "T3", "Ab tum sab mujhe dobara nahi dekhoge"),
    ("farewell_or_goodbye", "T3", "Main sab ko alvida keh raha hoon kyun ke zinda nahi rehna"),
]


# Benign hard negatives intentionally include suicide-related vocabulary in
# negated, historical, third-party, academic, idiomatic, or non-suicidal contexts.
BENIGN_SKELETONS = [
    ("negation", "Main khudkushi nahi karna chahta, mujhe support chahiye"),
    ("negation", "Mujhe marne ka irada nahi, bas exams ka stress hai"),
    ("negation", "Main apne aap ko hurt nahi karunga, main safe hoon"),
    ("negation", "Nahi, main zinda rehna chahta hoon aur help le raha hoon"),
    ("negation", "Mujhe khud ko nuqsan dene ka koi plan nahi hai"),
    ("past_recovery", "Pehle mushkil waqt tha, ab main behtar aur safe hoon"),
    ("past_recovery", "College ke waqt udaas tha, ab therapy se kaafi madad mili"),
    ("past_recovery", "Saalon pehle khudkushi ke khayalat aaye thay, ab nahi"),
    ("past_recovery", "Main pehle self harm karta tha, ab recovery mein hoon"),
    ("third_party", "Meri dost ne kaha ke woh bohat udaas hai, main uski madad kaise karun"),
    ("third_party", "Mere cousin ne film mein suicide ka scene dekha"),
    ("third_party", "Someone online ne khud ko nuqsan dene ki baat ki, main report karun?"),
    ("third_party", "Mera bhai stress mein hai, us se kaise baat karun"),
    ("academic_or_media", "School project ke liye suicide prevention par maloomat chahiye"),
    ("academic_or_media", "Novel mein aik kirdar khudkushi ka zikr karta hai"),
    ("academic_or_media", "News article mein suicide rates ka data parh raha tha"),
    ("academic_or_media", "Psychology class ke liye depression symptoms samjha dein"),
    ("idiom_or_hyperbole", "Yaar exam itna mushkil hai ke mar jaunga lol"),
    ("idiom_or_hyperbole", "Garmi se mar raha hoon, fan chala do"),
    ("idiom_or_hyperbole", "Traffic mujhe maar dalega, bohat jam laga hua hai"),
    ("idiom_or_hyperbole", "Main hans hans ke mar gaya, woh joke zabardast tha"),
    ("railway_benign", "Railway track par train chalti hai"),
    ("railway_benign", "Main railway track par train ka wait kar raha hoon"),
    ("railway_benign", "Rail ki patri ke paas station ka board laga hai"),
    ("wellbeing_without_suicide", "Parhai ka bohat stress hai, lekin main safe hoon"),
]


def _surface_variants(text: str) -> list[tuple[str, str]]:
    """Return ten label-preserving conversational, casing, and spelling forms."""
    spelling = text
    for old, new in (
        ("khudkushi", "khud kushi"),
        ("mujhe", "mujhay"),
        ("nahi", "nai"),
        ("hoon", "hun"),
        ("zindagi", "zindagee"),
        ("bohat", "bohot"),
        ("hai", "hay"),
    ):
        spelling = spelling.replace(old, new)

    variants = [
        ("plain", text),
        ("yaar_prefix", f"Yaar, {text}"),
        ("suno_prefix", f"Suno, {text}"),
        ("please_prefix", f"Please meri baat suno: {text}"),
        ("code_switch_prefix", f"Honestly, {text}"),
        ("please_suffix", f"{text}, please"),
        ("yaar_suffix", f"{text} yaar"),
        ("ellipsis", f"{text}..."),
        ("spelling_variant", spelling if spelling != text else f"{text} na"),
        ("uppercase", text.upper()),
    ]
    assert len({message for _, message in variants}) == 10, text
    return variants


def build_cases() -> list[dict]:
    cases = []
    groups = [
        (1, [(category, tier, text) for category, tier, text in CRISIS_SKELETONS]),
        (0, [(category, "NEG", text) for category, text in BENIGN_SKELETONS]),
    ]
    for label, skeletons in groups:
        for skeleton_index, (category, tier_or_none, text) in enumerate(skeletons, 1):
            for style, variant_text in _surface_variants(text):
                case_number = len(cases) + 1
                cases.append({
                    "id": f"RU-SYN-{case_number:04d}",
                    "skeleton_id": f"{'CR' if label else 'BN'}-{skeleton_index:02d}",
                    "text": variant_text,
                    "label": label,
                    "label_text": "crisis" if label else "benign",
                    "category": category,
                    "severity_tier": tier_or_none or "NEG",
                    "script_style": style,
                    "source": "synthetic_template_variant",
                    "reviewer_status": "needs_native_speaker_review",
                })
    return cases


def _wilson_interval(successes: int, total: int) -> list[float] | None:
    if not total:
        return None
    z = 1.96
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)]


def _metrics(rows: list[dict], key: str) -> dict:
    positive = [row for row in rows if row[key] == 1]
    tp = sum(row["predicted_crisis"] for row in positive)
    fn = len(positive) - tp
    negative = [row for row in rows if row[key] == 0]
    tn = sum(not row["predicted_crisis"] for row in negative)
    fp = len(negative) - tn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "cases": len(rows), "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "recall": round(recall, 4), "precision": round(precision, 4),
        "specificity": round(specificity, 4), "f1": round(f1, 4),
        "recall_wilson_95": _wilson_interval(tp, tp + fn),
        "specificity_wilson_95": _wilson_interval(tn, tn + fp),
    }


def main() -> int:
    cases = build_cases()
    if len(cases) != 500 or len({case["id"] for case in cases}) != 500:
        raise RuntimeError(f"Expected 500 unique cases, got {len(cases)}")

    dataset = {
        "meta": {
            "name": "Roman Urdu synthetic 500-case diagnostic evaluation",
            "split": "synthetic_diagnostic_not_holdout",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "case_count": 500,
            "positive_cases": 250,
            "negative_cases": 250,
            "unique_skeletons": 50,
            "variants_per_skeleton": 10,
            "warning": (
                "Synthetic, template-derived examples. Ten variants share each of 50 skeletons; "
                "case-level metrics are correlated and must not be reported as independent "
                "real-world accuracy or clinical validation. Native-speaker review is required."
            ),
        },
        "cases": cases,
    }
    OUTPUT.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = []
    for case in cases:
        result = evaluate_crisis_pipeline(case["text"], allow_ml_fallback=False)
        rows.append({**case, "predicted_crisis": bool(result.get("is_crisis")),
                     "prediction_source": result.get("source", "")})

    summary = _metrics(rows, "label")
    per_category = {
        category: _metrics([row for row in rows if row["category"] == category], "label")
        for category in sorted({row["category"] for row in rows})
    }
    by_skeleton: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_skeleton[row["skeleton_id"]].append(row)
    skeletons = []
    for skeleton_id, group in sorted(by_skeleton.items()):
        correct = sum(row["predicted_crisis"] == bool(row["label"]) for row in group)
        skeletons.append({"skeleton_id": skeleton_id, "correct": correct, "cases": len(group),
                          "all_correct": correct == len(group)})

    failures = [row for row in rows if row["predicted_crisis"] != bool(row["label"])]
    report = {
        "dataset": str(OUTPUT.relative_to(ROOT)),
        "summary": summary,
        "per_category": per_category,
        "skeletons_all_variants_correct": sum(item["all_correct"] for item in skeletons),
        "skeleton_count": len(skeletons),
        "failure_examples": [
            {"id": row["id"], "expected": row["label_text"],
             "predicted_crisis": row["predicted_crisis"],
             "category": row["category"], "text": row["text"]}
            for row in failures[:30]
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
