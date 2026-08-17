# MindGuard ML starting point

MindGuard needs separate components because the available files represent
different tasks and incompatible labels:

1. **Crisis-risk classifier** — `archive (5).zip/file1.csv`. `archive (6).zip`
   contains an identical copy and must not be added again.
2. **Sentiment classifier** — `archive (4).zip/.../Pos_Neut_Neg.csv` has
   positive, neutral, and negative labels.
3. **Intent classifier** — `archive.zip/intents.json` has 80 intents but only
   232 example patterns. It needs more examples before a reliable 80-class
   model can be claimed.
4. **Response layer** — the Context/Response and CounselChat files are response
   data. Start with curated retrieval or reviewed templates; do not mix them
   into the classifiers.

The provided notebooks are references, not runnable project pipelines. One
expects a missing `Combined Data.csv`; the other expects missing files such as
`Suicide_Detection.csv` and `glove.840B.300d.pkl`, uses an input-length mismatch,
and has no untouched test set.

## Training runs

From the project root in PowerShell:

```powershell
python ml/train_crisis.py
python ml/train_sentiment.py
python ml/train_intent.py
```

The command reads the ZIP directly and creates:

- `artifacts/crisis_detector.joblib` and `.metrics.json`
- `artifacts/sentiment_classifier.joblib` and `.metrics.json`
- `artifacts/intent_classifier.joblib` and `.metrics.json`

All trainers read the cleaned `dataset/processed/<task>/train.csv`,
`validation.csv`, and `test.csv` files. Crisis threshold selection uses only
validation data. Intent confidence selection also uses validation data; the
small out-of-scope file is reported separately as a diagnostic.

Try the saved model:

```powershell
python ml/predict_crisis.py "I feel overwhelmed and need someone to talk to"
```

## Required application flow

```text
message
  -> deterministic crisis rules + crisis classifier
       -> risk: fixed, human-reviewed safety response and locale resources
       -> no risk: intent classifier + sentiment classifier
                    -> curated response/template retrieval
```

This model is a research/demo baseline, not a diagnosis. A crisis classifier
must never be the only safety control. Validate it on manually reviewed,
out-of-source examples before the project is demonstrated or deployed.
