# Reviewer Sheets — Roman Urdu Crisis Benchmark

CONTENT NOTE: These messages include crisis and self-harm language. This work is for adults (18+) only, and it is voluntary - you may skip any case, take breaks, or stop at any time, with no pressure. If anything stays with you afterwards, message the project owner (Saqib Tariq - he shares his contact directly), or call Umang Helpline 0311-7786264 (free, 24/7; verified 2026-10-06 against umang.com.pk and the WHO EMRO directory). You are helping make a safety tool better, and that matters.

## Before you start
Read **docs/roman_urdu_labeling_guide.md** (v1.1, in the repo) — it defines the
labels, the tier rules, and the rules for hyperbole, negation, sarcasm,
religious phrases, third-party messages, harm-to-others, and past attempts.

## Files
- `pilot_40.csv` — 40 cases. Label these first; they measure how well the guide
  works (agreement between reviewers). If agreement is low, the guide gets
  revised and you re-label a fresh pilot.
- `dev_sheet.csv` — ~120 more cases, same rules (sent out after the pilot is
  reviewed).
- `add_your_own_cases.csv` — **the most valuable sheet.** Write REAL-sounding
  messages *you* think a Pakistani user might send — both crisis and everyday
  ones, in any style (pure Roman Urdu, English mixed in, texting shorthand).
  Put `crisis`, `distress`, `benign`, or `unsure` as your label. These become
  TEST-2: the holdout nobody tunes against, so please don't discuss them with
  the project owner.

## Columns
`your_label`: crisis / distress / benign / unsure ·
`tier_if_crisis`: 1 / 2 / 3 (only if crisis) ·
`natural`: yes / stiff / wrong — flag anything that sounds Hindi-flavoured or
unnatural for Pakistani speakers ·
`notes`: free text ("history", "possibly self", "harm_others", or why unsure).

## Rules
- Label alone, at your own pace. Don't discuss with other reviewers until done.
- `unsure` is a valid answer and is genuinely useful.
- Your name is never stored — sheets are numbered reviewer_1/2/3 only.
- Return sheets to Saqib. Do not upload them anywhere public.
- After the pilot: disagreed cases become worked examples in guide v1.1, then
  the full sheets go out.
