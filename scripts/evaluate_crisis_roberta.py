"""
scripts/evaluate_crisis_roberta.py
-------------------------------------------------------------------------
Evaluates the fine-tuned crisis RoBERTa model (artifacts/huggingface_crisis_roberta)
on:
  1. The held-out test split (dataset/processed/crisis/test.csv)
  2. The 300-case benchmark sets in tests/data/

Outputs metrics (accuracy / precision / recall / F1 / ROC-AUC, confusion
matrix, threshold sweep, per-category breakdown, latency) to stdout and to
artifacts/model_evaluation_report.json.
"""

import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from transformers import AutoModelForSequenceClassification, AutoTokenizer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / "artifacts" / "huggingface_crisis_roberta"
TEST_CSV = PROJECT_ROOT / "dataset" / "processed" / "crisis" / "test.csv"
BENCHMARKS = {
    "english_crisis_benchmark_300": PROJECT_ROOT / "tests" / "data" / "english_crisis_benchmark_300.json",
    "english_crisis_benchmark_new_300": PROJECT_ROOT / "tests" / "data" / "english_crisis_benchmark_new_300.json",
    "crisis_nlp_benchmark_dataset": PROJECT_ROOT / "tests" / "data" / "crisis_nlp_benchmark_dataset.json",
    "generated_crisis_eval_dataset_v2": PROJECT_ROOT / "tests" / "data" / "generated_crisis_eval_dataset_v2.json",
}
REPORT_PATH = PROJECT_ROOT / "artifacts" / "model_evaluation_report.json"
MAX_LENGTH = 128
BATCH_SIZE = 64


@torch.no_grad()
def predict_probs(model, tokenizer, texts, batch_size=BATCH_SIZE):
    """Returns P(crisis) for each text."""
    probs = []
    model.eval()
    for i in range(0, len(texts), batch_size):
        batch = [str(t) for t in texts[i : i + batch_size]]
        enc = tokenizer(batch, truncation=True, max_length=MAX_LENGTH, padding=True, return_tensors="pt")
        logits = model(**enc).logits
        probs.extend(torch.softmax(logits, dim=-1)[:, 1].tolist())
    return np.array(probs)


def metrics_from_probs(y_true, probs, threshold=0.5):
    preds = (probs >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, preds, labels=[0, 1]).ravel()
    out = {
        "n": int(len(y_true)),
        "threshold": threshold,
        "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
        "accuracy": round(accuracy_score(y_true, preds), 4),
        "precision": round(precision_score(y_true, preds, zero_division=0), 4),
        "recall": round(recall_score(y_true, preds, zero_division=0), 4),
        "f1": round(f1_score(y_true, preds, zero_division=0), 4),
        "fnr": round(fn / (fn + tp), 4) if (fn + tp) else 0.0,
        "fpr": round(fp / (fp + tn), 4) if (fp + tn) else 0.0,
    }
    try:
        out["roc_auc"] = round(float(roc_auc_score(y_true, probs)), 4)
    except ValueError:
        out["roc_auc"] = None
    return out


def main():
    print("=" * 78)
    print("   MINDGUARD CRISIS ROBERTA - MODEL EVALUATION")
    print("=" * 78)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"\n[SETUP] device={device.upper()} | model={MODEL_DIR.name}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR).to(device)
    id2label = model.config.id2label
    pos_idx = [i for i, l in id2label.items() if "crisis" in str(l).lower() and "non" not in str(l).lower()]
    print(f"        labels: {id2label} | positive class index: {pos_idx}")

    report = {"model": str(MODEL_DIR), "device": device, "datasets": {}}

    # ------------------------------------------------------------------
    # 1. Held-out test split
    # ------------------------------------------------------------------
    print(f"\n[1] Held-out test split: {TEST_CSV.name}")
    df = pd.read_csv(TEST_CSV)
    texts = df["text"].astype(str).tolist()
    labels = df["label"].astype(int).tolist()

    t0 = time.time()
    probs = predict_probs(model, tokenizer, texts)
    elapsed = time.time() - t0
    print(f"    {len(texts):,} examples scored in {elapsed:.1f}s "
          f"({len(texts)/elapsed:.0f} samples/s, {1000*elapsed/len(texts):.1f} ms/sample)")

    test_metrics = metrics_from_probs(labels, probs, threshold=0.5)
    test_metrics["latency_ms_per_sample"] = round(1000 * elapsed / len(texts), 2)
    report["datasets"]["test_split"] = test_metrics
    for k in ["n", "tp", "fp", "tn", "fn", "accuracy", "precision", "recall", "f1", "roc_auc", "fnr", "fpr"]:
        print(f"    {k:>12s}: {test_metrics[k]}")

    sweep = {str(t): metrics_from_probs(labels, probs, threshold=t) for t in [0.3, 0.4, 0.5, 0.6, 0.7]}
    report["datasets"]["test_split"]["threshold_sweep"] = sweep
    print("    threshold sweep (recall / precision / f1 / fnr):")
    for t, m in sweep.items():
        print(f"      thr={t}: recall={m['recall']:.4f} precision={m['precision']:.4f} "
              f"f1={m['f1']:.4f} fnr={m['fnr']:.4f} fp={m['fp']} fn={m['fn']}")

    # ------------------------------------------------------------------
    # 2. Benchmarks
    # ------------------------------------------------------------------
    for name, path in BENCHMARKS.items():
        print(f"\n[2] Benchmark: {name}")
        cases = json.load(open(path, encoding="utf-8"))
        texts = [c["text"] for c in cases]
        y_true = [1 if str(c.get("expected_crisis", c.get("expected_label", ""))).lower() in ("true", "1", "crisis", "yes") else 0 for c in cases]

        probs = predict_probs(model, tokenizer, texts)
        m = metrics_from_probs(y_true, probs, threshold=0.5)

        # per-category breakdown
        cat_stats = {}
        preds = (probs >= 0.5).astype(int)
        for c, yt, yp in zip(cases, y_true, preds):
            cat = c.get("category", "unknown")
            s = cat_stats.setdefault(cat, {"n": 0, "tp": 0, "fp": 0, "tn": 0, "fn": 0})
            s["n"] += 1
            if yp == 1 and yt == 1: s["tp"] += 1
            elif yp == 1 and yt == 0: s["fp"] += 1
            elif yp == 0 and yt == 0: s["tn"] += 1
            else: s["fn"] += 1
        m["per_category"] = cat_stats
        report["datasets"][name] = m

        print(f"    n={m['n']} | acc={m['accuracy']:.4f} prec={m['precision']:.4f} "
              f"rec={m['recall']:.4f} f1={m['f1']:.4f} auc={m['roc_auc']}")
        print(f"    TP={m['tp']} FP={m['fp']} TN={m['tn']} FN={m['fn']}")
        print("    per-category (recall on crisis cats / specificity on non-crisis cats):")
        for cat, s in sorted(cat_stats.items()):
            crisis_cat = s["tp"] + s["fn"] > 0
            if crisis_cat:
                r = s["tp"] / (s["tp"] + s["fn"])
                print(f"      {cat:32s} n={s['n']:3d} [CRISIS]    recall={r:5.1%} (fn={s['fn']})")
            else:
                sp = s["tn"] / (s["tn"] + s["fp"]) if (s["tn"] + s["fp"]) else float("nan")
                print(f"      {cat:32s} n={s['n']:3d} [NON-CRISIS] spec={sp:5.1%} (fp={s['fp']})")

        # worst false negatives (missed crisis cases, by predicted prob)
        fn_cases = [
            {"text": c["text"][:140], "category": c.get("category"), "p_crisis": round(float(p), 4)}
            for c, yt, yp, p in zip(cases, y_true, preds, probs) if yt == 1 and yp == 0
        ]
        fn_cases.sort(key=lambda x: x["p_crisis"], reverse=True)
        if fn_cases:
            print(f"    top missed crisis cases (highest P(crisis) among FN):")
            for fc in fn_cases[:5]:
                print(f"      p={fc['p_crisis']:.3f} [{fc['category']}] {fc['text']}")
        m["false_negatives"] = fn_cases

    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n[DONE] Full report saved to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
