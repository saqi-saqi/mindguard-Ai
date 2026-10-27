# MindGuard Multi-Label Wellbeing Model: Training & Research Notes

## 1. Overview
MindGuard incorporates an independent, multi-label wellbeing layer that operates alongside its deterministic Tier 1 crisis safety architecture. This layer decouples non-clinical wellbeing traits (`stress`, `anxiety_signals`, `depression_signals`) from critical safety-risk classifications (`suicide_ideation`, `suicide_intent`, `suicide_plan_or_means`, `harm_to_others`).

To support future ML capabilities beyond deterministic extraction and current classifier outputs, this document outlines candidate research datasets, evaluation criteria, and rigorous data governance guidelines.

---

## 2. Candidate Research Datasets

| Dataset / Baseline | Target Domain | Research Role | Access / Licensing Considerations |
| :--- | :--- | :--- | :--- |
| **Dreaddit** | Stress identification | Benchmarking stress vs. non-stress in social narratives | Public academic research dataset (Reddit domains). English only. |
| **GoEmotions** | Fine-grained emotion signals | Calibrating nuanced emotional expressions (fear, grief, relief, joy) | Open dataset (58k Reddit comments, 27 emotion labels + neutral). |
| **DAIC-WOZ** | Depression & distress markers | Controlled clinical multimodal depression research | Restricted academic research license only; requires formal agreement. |
| **eRisk (CLEF)** | Early risk detection of depression & self-harm | Controlled sequential evaluation of pathological distress over time | Restricted academic evaluation dataset; strict competition usage protocols. |
| **MentalBERT** | Pre-trained domain baseline | Domain-adapted masked language model for mental health research | Open model weights on Hugging Face (trained on Reddit mental health subreddits). English baseline only. |

---

## 3. Cultural & Linguistic Limitations of Public English Benchmarks

1. **Language & Dialect Mismatch**:
   - Public datasets (Dreaddit, GoEmotions, MentalBERT) are almost exclusively English social media corpora.
   - They fail to capture code-switching, Roman Urdu idioms (e.g., *"dimagh fat raha hai"*, *"bohot tension hai"*, *"dil ghabra raha hai"*), colloquial nuances, and Urdu script semantics prevalent in Pakistan.
2. **Contextual Expression Differences**:
   - Somatic manifestations of emotional distress in South Asian populations frequently present through physical metaphors (*"zehni dabao"*, *"sans phoolna"*, *"bistar se uthne ki himmat nahi"*) rather than Western psychiatric terminologies.
3. **Validation Requirements**:
   - Public English datasets **cannot and must not be used as sole production validation** for users in Pakistan or Roman Urdu environments. Localized validation sets are mandatory before deployment.

---

## 4. Production Training Governance & Ethical Principles

1. **Consent & Privacy Invariants**:
   - **User conversations must never be silently ingested into a training dataset.**
   - Any training corpus must consist solely of consented, anonymized, and vetted research data or synthetic clinical vignettes.
2. **Local Review & Oversight**:
   - Annotation guidelines and model outputs must be reviewed by local mental health professionals familiar with linguistic and socio-cultural contexts in Pakistan.
3. **Data Anonymization**:
   - Strict scrubbing of personally identifiable information (PII), geographic names, telephone numbers, and unique biographical markers prior to training ingestion.

---

## 5. Model Evaluation & Safety Guardrail Criteria

Before any candidate model is integrated via `WellbeingMultiLabelModelAdapter`:
1. **Per-Label Performance**:
   - High per-label recall and precision for `stress`, `anxiety_signals`, and `depression_signals`.
   - Calibration curves must be validated across varied confidence thresholds.
2. **False Positive Suppression**:
   - Explicit negative validation against idioms, hyperbole (*"this exam is killing me"*, *"dying of laughter"*), past-resolved recovery, and academic/fictional frames.
3. **Crisis Precedence Preservation (Zero Regression)**:
   - A multi-label wellbeing classifier must **never override or downgrade** explicit deterministic suicide or harm-to-others outcomes (`COMBINED_HIGH_CRISIS`, `THREAT_AGAINST_USER`, `HARM_TO_OTHERS_RISK`, `REPORTED_THREAT_TO_OTHERS`, `HIGH_CRISIS`).
   - The model must safely fail-open to deterministic triage if offline or uncalibrated.
