# MindGuard Safety Incident Response Procedure

**Status:** Academic prototype operating procedure. This document does not replace clinical, legal, or emergency-service protocols.

## Immediate user safety

MindGuard provides an always-available **Get urgent help** action in chat, regardless of classifier output. It must immediately show crisis resources; it must never require a feedback form or a new model assessment first.

MindGuard does not automatically contact emergency services, a trusted contact, or another third party from a model prediction. Any future escalation workflow needs explicit user consent, clinical review, lawful authority, and an approved operating procedure.

## Possible missed crisis signal

1. Treat a credible report as a safety incident immediately; do not start with rule debugging.
2. Show urgent-help resources and encourage immediate local emergency or professional support when danger is imminent.
3. Record only an incident ID, timestamp, model/rule version, and de-identified category. Do not copy chat text into general logs or tickets.
4. Restrict access to any approved forensic record and follow consent, retention, and applicable legal requirements.
5. Have the designated safety owner and qualified clinical/safety reviewer assess the incident.
6. Add an approved de-identified regression case only after review, then rerun regression and independent evaluations before release.
7. Roll back or disable a release with a material, repeatable safety regression.

## Incorrect crisis signal

1. Use neutral, non-diagnostic language and provide a user-controlled **I'm safe for now** option.
2. Keep normal chat and help resources available; never punish, lock out, or label the user.
3. Store only voluntary metadata (`outcome` and `source`) in safety events. Never store free-text explanations, message contents, phone numbers, or location through safety feedback.
4. Review aggregate de-identified feedback. Do not weaken a safety rule to address one false positive without measuring recall impact.

## Release controls

- The 222-case aggressive suite and approved regression fixture must pass completely.
- Report development and policy-isolated evaluation results separately.
- Review changed crisis rules for false negatives, false positives, negation, historical context, academic/media context, idioms, and regional-language coverage.
