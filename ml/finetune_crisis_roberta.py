"""
MindGuard - Fine-Tuning DistilRoBERTa on Crisis/Suicide Detection Dataset
-------------------------------------------------------------------------
This script fine-tunes 'distilroberta-base' on MindGuard's cleaned crisis dataset:
  dataset/processed/crisis/train.csv
  dataset/processed/crisis/validation.csv
  dataset/processed/crisis/test.csv
"""

import sys
from pathlib import Path

try:
    import pandas as pd
    import torch
    from datasets import Dataset
    from transformers import (
        AutoTokenizer,
        AutoModelForSequenceClassification,
        Trainer,
        TrainingArguments,
    )
except ImportError:
    print("\n[ERROR] Missing required packages.")
    print("Please install them by running:")
    print("  pip install torch transformers datasets pandas accelerate\n")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "dataset" / "processed" / "crisis"
OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "huggingface_crisis_roberta"


def load_data():
    train_df = pd.read_csv(DATA_DIR / "train.csv")
    val_df = pd.read_csv(DATA_DIR / "validation.csv")
    test_df = pd.read_csv(DATA_DIR / "test.csv")

    label2id = {"non_suicide": 0, "suicide": 1}
    id2label = {0: "non_suicide", 1: "suicide"}

    train_df["label"] = train_df["label"].map(label2id)
    val_df["label"] = val_df["label"].map(label2id)
    test_df["label"] = test_df["label"].map(label2id)

    return (
        Dataset.from_pandas(train_df),
        Dataset.from_pandas(val_df),
        Dataset.from_pandas(test_df),
        label2id,
        id2label,
    )


def main():
    print("=======================================================")
    print("       FINE-TUNING DISTILROBERTA FOR CRISIS RISK       ")
    print("=======================================================")
    
    print("\n1. Loading preprocessed crisis datasets...")
    train_ds, val_ds, test_ds, label2id, id2label = load_data()

    model_name = "distilroberta-base"
    print(f"\n2. Loading pretrained tokenizer and model: '{model_name}'...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=2,
        label2id=label2id,
        id2label=id2label
    )

    def tokenize_fn(examples):
        return tokenizer(examples["text"], truncation=True, max_length=128)

    print("\n3. Tokenizing datasets...")
    train_ds = train_ds.map(tokenize_fn, batched=True)
    val_ds = val_ds.map(tokenize_fn, batched=True)
    test_ds = test_ds.map(tokenize_fn, batched=True)

    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=2e-5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=32,
        num_train_epochs=3,
        weight_decay=0.01,
        load_best_model_at_end=True,
        metric_for_best_model="loss",
        logging_steps=50,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        processing_class=tokenizer,
    )

    print("\n4. Starting model fine-tuning...")
    trainer.train()

    print(f"\n5. Saving fine-tuned model and tokenizer to: {OUTPUT_DIR}...")
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print("\n[SUCCESS] Fine-tuning complete! Model is ready for inference.")


if __name__ == "__main__":
    main()
