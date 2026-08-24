"""
ml/finetune_crisis_roberta.py
-------------------------------------------------------------------------
Fine-tunes 'distilroberta-base' on MindGuard's 140k crisis dataset:
  dataset/processed/crisis/train.csv
  dataset/processed/crisis/validation.csv
  dataset/processed/crisis/test.csv
"""

import sys
import os
import json
from pathlib import Path

# Fix console encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    import pandas as pd
    import numpy as np
    import torch
    from datasets import Dataset
    from transformers import (
        AutoTokenizer,
        AutoModelForSequenceClassification,
        Trainer,
        TrainingArguments,
    )
    from sklearn.metrics import precision_recall_fscore_support, roc_auc_score
except ImportError:
    print("\n[ERROR] Missing required packages.")
    print("Please install them by running:")
    print("  pip install torch transformers datasets pandas accelerate scikit-learn\n")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "dataset" / "processed" / "crisis"
OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "huggingface_crisis_roberta"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_data():
    train_df = pd.read_csv(DATA_DIR / "train.csv")
    val_df = pd.read_csv(DATA_DIR / "validation.csv")
    test_df = pd.read_csv(DATA_DIR / "test.csv")

    def clean_labels(df):
        # Handle both integer 0/1 and string labels safely
        mapping = {"suicide": 1, "non_suicide": 0, "non-suicide": 0, "1": 1, "0": 0, 1: 1, 0: 0}
        df["label"] = df["label"].map(lambda x: mapping.get(x, mapping.get(str(x).lower(), int(x) if str(x).isdigit() else 0)))
        df["text"] = df["text"].astype(str)
        return df.dropna(subset=["text", "label"])

    train_df = clean_labels(train_df)
    val_df = clean_labels(val_df)
    test_df = clean_labels(test_df)

    label2id = {"non_suicide": 0, "suicide": 1}
    id2label = {0: "non_suicide", 1: "suicide"}

    return (
        Dataset.from_pandas(train_df),
        Dataset.from_pandas(val_df),
        Dataset.from_pandas(test_df),
        label2id,
        id2label,
    )


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    probs = torch.softmax(torch.tensor(logits), dim=-1)[:, 1].numpy()
    preds = (probs >= 0.50).astype(int)

    precision, recall, f1, _ = precision_recall_fscore_support(labels, preds, average="binary", zero_division=0)
    try:
        auc = float(roc_auc_score(labels, probs))
    except Exception:
        auc = 0.0

    return {
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "roc_auc": round(auc, 4),
    }


def main():
    print("=======================================================")
    print("       FINE-TUNING DISTILROBERTA FOR CRISIS RISK       ")
    print("=======================================================")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"\n[INFO] Training Device: {device.upper()}")
    if device == "cpu":
        print("  -> Running on CPU. For 10x faster training, run in Google Colab with free T4 GPU.")

    print("\n1. Loading preprocessed crisis datasets...")
    train_ds, val_ds, test_ds, label2id, id2label = load_data()
    print(f"  • Train: {len(train_ds):,} | Val: {len(val_ds):,} | Test: {len(test_ds):,}")

    model_name = "distilroberta-base"
    print(f"\n2. Loading pretrained tokenizer and model: '{model_name}'...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=2,
        label2id=label2id,
        id2label=id2label,
    )

    def tokenize_fn(examples):
        return tokenizer(examples["text"], truncation=True, max_length=128, padding="max_length")

    print("\n3. Tokenizing datasets...")
    train_ds = train_ds.map(tokenize_fn, batched=True, batch_size=1000)
    val_ds = val_ds.map(tokenize_fn, batched=True, batch_size=1000)

    # Automatically adapt batch size for CPU vs GPU
    batch_size = 32 if device == "cuda" else 8
    epochs = 3

    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=2e-5,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size * 2,
        num_train_epochs=epochs,
        weight_decay=0.01,
        warmup_ratio=0.1,
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        logging_steps=100,
        save_total_limit=2,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        processing_class=tokenizer,
        compute_metrics=compute_metrics,
    )

    print("\n4. Starting model fine-tuning...")
    trainer.train()

    print(f"\n5. Saving fine-tuned model and tokenizer to: {OUTPUT_DIR}...")
    trainer.save_model(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))

    print("\n[SUCCESS] Fine-tuning complete! Model is ready for inference.")


if __name__ == "__main__":
    main()
