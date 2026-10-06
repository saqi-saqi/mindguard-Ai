# Reviewer Sheets — Roman Urdu Crisis Benchmark

CONTENT NOTE: These messages include crisis and self-harm language. You may skip any case, take breaks, or stop at any time - this is voluntary and never urgent. If anything stays with you afterwards, please talk to someone you trust, or contact Umang Helpline 0311-7786264 (free, 24/7). You are helping make a safety tool better, and that matters.

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
