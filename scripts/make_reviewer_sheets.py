"""
Stage 1 quality + reviewer tooling:
  1. Naturalness audit sample: 30 random DEV cases -> artifacts/naturalness_audit_sample.md
     (owner marks each natural / stiff / wrong; >20% stiff|wrong => regenerate cohort)
  2. Reviewer sheets (blind, no labels): pilot 40 + full DEV sheet (~120 stratified)
     + blank "add your own cases" template -> artifacts/reviewer_sheets/
  3. README with the content note + instructions.
Deterministic (seed 42). DEV-only — the frozen TEST file is never touched here.
"""
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

if __name__ == "__main__" or True:
    pass
ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "tests" / "data" / "roman_urdu_benchmark_dev.json"
SHEETS = ROOT / "artifacts" / "reviewer_sheets"
SEED = 42

CONTENT_NOTE = (
    "CONTENT NOTE: These messages include crisis and self-harm language. "
    "You may skip any case, take breaks, or stop at any time - this is voluntary "
    "and never urgent. If anything stays with you afterwards, please talk to "
    "someone you trust, or contact Umang Helpline 0311-7786264 (free, 24/7). "
    "You are helping make a safety tool better, and that matters."
)


def main():
    rng = random.Random(SEED)
    dev = json.loads(DEV.read_text(encoding="utf-8"))["cases"]
    SHEETS.mkdir(parents=True, exist_ok=True)

    # ---- 1. naturalness audit sample (DEV only) ----
    sample = rng.sample(dev, 30)
    lines = [
        "# Naturalness Audit — 30 random DEV cases (seed 42)",
        "",
        "Mark each case **natural** / **stiff** / **wrong**. If >20% are stiff or wrong,",
        "the affected cohorts are regenerated before Stage 2 (corpus rebuilt, split",
        "re-frozen — no TEST evaluation has happened yet, so this is a version bump,",
        "not tuning).",
        "",
        "| # | id | category | style | text | your mark |",
        "|---|----|----------|-------|------|-----------|",
    ]
    for i, c in enumerate(sample, 1):
        lines.append(f"| {i} | {c['id']} | {c['category']} | {c['script_style']} | {c['text']} | |")
    (ROOT / "artifacts" / "naturalness_audit_sample.md").write_text("\n".join(lines), encoding="utf-8")

    # ---- 2. reviewer sheets ----
    by_cat = defaultdict(list)
    for c in dev:
        by_cat[c["category"]].append(c)
    for cat in by_cat:
        rng.shuffle(by_cat[cat])

    pilot = []
    full = []
    cats = sorted(by_cat)
    # pilot: 40 stratified (round-robin one per category until 40)
    i = 0
    while len(pilot) < 40:
        for cat in cats:
            if len(pilot) < 40 and i < len(by_cat[cat]):
                c = by_cat[cat][i]
                if c not in pilot:
                    pilot.append(c)
        i += 1
    # full sheet: ~120 stratified, excludes pilot cases
    target = 120
    i = 0
    while len(full) < target and i < max(len(v) for v in by_cat.values()):
        for cat in cats:
            if len(full) < target and i < len(by_cat[cat]):
                c = by_cat[cat][i]
                if c not in pilot and c not in full:
                    full.append(c)
        i += 1

    def write_sheet(path, cases, own_cases=False):
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["case_id", "text", "your_label (crisis/distress/benign/unsure)",
                        "tier_if_crisis (1/2/3)", "notes"])
            for c in cases:
                w.writerow([c["id"], c["text"], "", "", ""])
            if own_cases:
                for _ in range(10):
                    w.writerow(["(write your own)", "", "", "", ""])
        print("sheet:", path.name, f"({len(cases)} cases)")

    write_sheet(SHEETS / "pilot_40.csv", pilot)
    write_sheet(SHEETS / "dev_sheet.csv", full)
    write_sheet(SHEETS / "add_your_own_cases.csv", [], own_cases=True)

    (SHEETS / "README.md").write_text(f"""# Reviewer Sheets — Roman Urdu Crisis Benchmark

{CONTENT_NOTE}

## Before you start
Read **docs/roman_urdu_labeling_guide.md** (in the repo) — it defines the labels,
severity tiers, and the rules for hyperbole, negation, sarcasm, religious
phrases, and third-party messages.

## Files
- `pilot_40.csv` — 40 cases. Label these first; they measure how well the guide
  works (agreement between reviewers). If agreement is low, the guide gets
  revised and you re-label a fresh pilot.
- `dev_sheet.csv` — ~120 more cases, same rules.
- `add_your_own_cases.csv` — **the most valuable sheet.** Write REAL-sounding
  messages *you* think a Pakistani user might send — both crisis and everyday
  ones, in any style (pure Roman Urdu, English mixed in, texting shorthand).
  Put `crisis`, `distress`, `benign`, or `unsure` as your label. These become
  TEST-2: the holdout nobody tunes against, so please don't discuss them with
  the project owner.

## Rules
- Label alone, at your own pace. Don't discuss with other reviewers until done.
- `unsure` is a valid answer and is genuinely useful.
- Your name is never stored — sheets are numbered reviewer_1/2/3 only.
- Return sheets to Saqib. Do not upload them anywhere public.
""", encoding="utf-8")
    print(f"pilot: {len(pilot)} | full sheet: {len(full)}")
    print(f"naturalness sample: {len(sample)} cases -> artifacts/naturalness_audit_sample.md")


if __name__ == "__main__":
    main()
