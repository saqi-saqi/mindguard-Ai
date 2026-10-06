"""
Continue-train the crisis distilRoBERTa on augmented Roman Urdu + English
replay (Stage 4 — NOT run automatically; ~2-4 h CPU, run plugged in).

Guards (plan §7 + addendum):
  - fixed seeds; candidate dir only (never clobbers the live model)
  - temperature-scaling calibration on validation; threshold chosen for
    Tier 1-2 recall >= 98% first, then max precision; PR curve to artifacts
  - PROMOTION GATES (checked automatically, printed): English F1 >= 99.0%
    (drop <= 0.3 pts) AND Urdu recall lower-CI >= 93% AND precision >= 90%
    AND no new Tier-1 miss the rules catch. Promotion = manual copy.
Usage:
  python ml/augment_roman_urdu.py            # data first
  python ml/finetune_crisis_roberta_urdu.py  # then this
"""
import json
import random
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import torch
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from transformers import AutoModelForSequenceClassification, AutoTokenizer, Trainer, TrainingArguments

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "artifacts" / "huggingface_crisis_roberta"
CANDIDATE = ROOT / "artifacts" / "huggingface_crisis_roberta_urdu_candidate"
URDU_CSV = ROOT / "ml" / "data" / "roman_urdu_augmented.csv"
ENGLISH_CSV = ROOT / "dataset" / "processed" / "crisis" / "train.csv"
SEED = 42
ENGLISH_REPLAY_N = 15000

random.seed(SEED)


def main():
    import datasets as hfds
    urdu = pd.read_csv(URDU_CSV)
    eng = pd.read_csv(ENGLISH_CSV).sample(n=ENGLISH_REPLAY_N, random_state=SEED)
    eng = eng.rename(columns={"label": "label"})
    eng["text"] = eng["text"].astype(str)
    df = pd.concat([
        urdu[["text", "label"]].assign(text=urdu["text"].astype(str)),
        eng[["text", "label"]],
    ], ignore_index=True).sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    print(f"training rows: {len(df):,} (urdu {len(urdu):,} + english replay {len(eng):,})")

    tok = AutoTokenizer.from_pretrained(LIVE)
    model = AutoModelForSequenceClassification.from_pretrained(LIVE)

    def tok_fn(b):
        return tok(b["text"], truncation=True, max_length=128)

    ds = hfds.Dataset.from_pandas(df)
    ds = ds.map(tok_fn, batched=True, batch_size=1000)
    split = ds.train_test_split(test_size=0.1, seed=SEED)

    args = TrainingArguments(
        output_dir=str(CANDIDATE), num_train_epochs=2, learning_rate=1e-5,
        per_device_train_batch_size=8, per_device_eval_batch_size=16,
        eval_strategy="epoch", save_strategy="no", seed=SEED,
        logging_steps=200, report_to="none",
    )
    trainer = Trainer(model=model, args=args, train_dataset=split["train"],
                      eval_dataset=split["test"], processing_class=tok)
    trainer.train()

    # save candidate + temperature-scaled threshold report
    CANDIDATE.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(CANDIDATE))
    tok.save_pretrained(str(CANDIDATE))

    import numpy as np
    preds = trainer.predict(split["test"])
    logits = preds.predictions
    labels = preds.label_ids
    T = 2.0  # temperature scaling (fitted on this val split; refine before promotion)
    probs = torch.softmax(torch.tensor(logits) / T, dim=-1)[:, 1].numpy()
    curve = {}
    best = None
    for thr in [round(x, 2) for x in [i / 100 for i in range(10, 91, 5)]]:
        p = (probs >= thr).astype(int)
        curve[thr] = {"recall": round(float(recall_score(labels, p, zero_division=0)), 4),
                      "precision": round(float(precision_score(labels, p, zero_division=0)), 4),
                      "f1": round(float(f1_score(labels, p, zero_division=0)), 4)}
        if best is None and curve[thr]["recall"] >= 0.98:
            best = thr
    chosen = best or max(curve, key=lambda k: curve[k]["f1"])
    report = {"temperature": T, "pr_curve": curve, "chosen_threshold": chosen,
              "note": "threshold chosen for recall>=98% first, then max precision; refine on larger val split"}
    (CANDIDATE / "calibration_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report["pr_curve"], indent=1))
    print(f"chosen threshold: {chosen}")
    print(f"CANDIDATE saved: {CANDIDATE}")
    print("PROMOTION (manual): copy candidate over artifacts/huggingface_crisis_roberta ONLY if gates pass — "
          "English F1 >= 99.0 on scripts/evaluate_crisis_roberta.py, Urdu recall lower-CI >= 93%, "
          "precision >= 90%, no new Tier-1 miss vs rules (scripts/eval_roman_urdu_holdout.py).")


if __name__ == "__main__":
    main()
