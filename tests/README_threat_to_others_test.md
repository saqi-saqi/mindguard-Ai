# MindGuard threat-to-others classification evaluation

## What this evaluates

This suite targets the behavior shown in the UI screenshot: `atif want to kill taim oor`.
It separates:

- a direct first-person threat (`HARM_TO_OTHERS_RISK`);
- a report that somebody else may harm another person (`THIRD_PARTY_REPORT`);
- a report that another person may harm the current user (`THIRD_PARTY_REPORT`, with relevant police guidance);
- self-harm and combined-risk controls;
- negation, fiction, games, idioms, historical context, typo/spacing variation, Roman Urdu, and mixed clauses.

It mocks `classify_semantically` so no live Gemini/Groq request is made and results are repeatable. The test deliberately contains edge cases that may fail with the current code; these are model/classifier gaps to investigate, not cases to delete to obtain a green run.

## Install

Copy `test_threat_to_others_context_matrix.py` into:

`tests/backend/test_threat_to_others_context_matrix.py`

## Run the tests

From the project root in PowerShell:

```powershell
.\.venv_clean\Scripts\python.exe -m pytest tests/backend/test_threat_to_others_context_matrix.py -v
```

Some tests may fail at first. Read the case IDs in the failure output to see whether the miss is actor attribution, a named target, spelling/spacing, a false positive from a joke/fiction/negation, or the wrong response template.

## Generate a diagnostic report

```powershell
.\.venv_clean\Scripts\python.exe tests/backend/test_threat_to_others_context_matrix.py
```

The script prints results by category and attempts to write:

`artifacts/threat_to_others_evaluation.json`

The expected labels distinguish `THIRD_PARTY_REPORT` from `is_crisis=True`: MindGuard's current schema treats a third-party report as a separate guidance route, not as proof that the reporting user is personally threatening someone. The relevant guidance should still mention appropriate emergency help.

## Scope note

This is a deterministic safety-classifier and endpoint-routing evaluation. It does not benchmark Groq's response quality or latency. It cannot establish clinical validation. Review any failing case carefully before changing rules; particularly, do not suppress an explicit live threat just because the message also contains “lol”, “just kidding”, or an unrelated negated clause.
