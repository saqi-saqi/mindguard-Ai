"""One-off measurement: 120-case edge-case benchmark + rule-layer latency.

Mirrors the CI gate (test_my_edge_cases_benchmark_gate) and times
evaluate_deterministic_crisis in isolation.
"""
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT))

os_ok = True
import os
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("USE_MONGOMOCK", "true")

from services.crisis_rules import evaluate_crisis_pipeline, evaluate_deterministic_crisis

cases = json.load(open(ROOT / "tests" / "data" / "my_edge_cases.json", encoding="utf-8"))

tp = fp = tn = fn = 0
failures = []
t0 = time.perf_counter()
for item in cases:
    res = evaluate_crisis_pipeline(item["text"], allow_ml_fallback=False)
    pred = res["is_crisis"]
    exp = item["expected_crisis"]
    if exp and pred:
        tp += 1
    elif not exp and not pred:
        tn += 1
    elif not exp and pred:
        fp += 1
        failures.append(("FP", item.get("category", "?"), item["text"]))
    else:
        fn += 1
        failures.append(("FN", item.get("category", "?"), item["text"]))
eval_s = time.perf_counter() - t0

n = len(cases)
acc = (tp + tn) / n
prec = tp / (tp + fp) if tp + fp else 0.0
rec = tp / (tp + fn) if tp + fn else 0.0
f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0

print("=== 120-case edge-case benchmark (rules-only, CI gate mode) ===")
print(f"total={n} tp={tp} fp={fp} tn={tn} fn={fn}")
print(f"accuracy={acc:.4f} precision={prec:.4f} recall={rec:.4f} f1={f1:.4f}")
for f in failures:
    print("FAIL:", f)

print()
print("=== rule-layer latency (evaluate_deterministic_crisis) ===")
texts = [c["text"] for c in cases]
# warmup
for t in texts[:20]:
    evaluate_deterministic_crisis(t)
samples = []
for rep in range(5):
    for t in texts:
        s = time.perf_counter()
        evaluate_deterministic_crisis(t)
        samples.append((time.perf_counter() - s) * 1000)
samples.sort()
print(f"runs={len(samples)} mean={statistics.mean(samples):.3f}ms "
      f"median={statistics.median(samples):.3f}ms p95={samples[int(len(samples)*0.95)]:.3f}ms "
      f"max={samples[-1]:.3f}ms")
