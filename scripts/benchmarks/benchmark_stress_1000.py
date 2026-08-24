"""
MindGuard - 1,000+ Edge-Case Automated Stress Test & Benchmark Suite
---------------------------------------------------------------------
Evaluates MindGuard's Crisis & Triage Engine against 1,000 real dataset samples
plus synthetic linguistic edge cases (negations, idioms, slang, false alarms).

Usage:
    python scripts/benchmarks/benchmark_stress_1000.py
"""

import sys
import json
import time
from pathlib import Path
import pandas as pd

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = WORKSPACE_ROOT
SERVER_DIR = WORKSPACE_ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from services.crisis_rules import evaluate_deterministic_crisis, is_contextual_or_negated
from services.huggingface_service import analyze_user_message, load_ml_pipelines

# Custom Synthetic Edge Cases (Tricky Linguistic Scenarios)
SYNTHETIC_EDGE_CASES = [
    # 1. Negation Edge Cases (False Alarm Protection)
    {"text": "I am NOT feeling suicidal, just tired after a long work day.", "expected_crisis": False, "category": "Negation"},
    {"text": "I am definitely not suicidal, please don't worry about me.", "expected_crisis": False, "category": "Negation"},
    {"text": "My friend told me a story about a suicide scene in a movie.", "expected_crisis": False, "category": "Negation"},
    {"text": "I used to feel suicidal 5 years ago, but today I am happy and healthy.", "expected_crisis": False, "category": "Negation"},
    {"text": "I never want to end my life, life is too precious.", "expected_crisis": False, "category": "Negation"},
    
    # 2. Metaphors, Idioms & Colloquialisms
    {"text": "LOL that joke was so funny I'm dying of laughter!", "expected_crisis": False, "category": "Metaphor/Idiom"},
    {"text": "This math exam is literally killing me.", "expected_crisis": False, "category": "Metaphor/Idiom"},
    {"text": "I'm starving to death right now, let's get food.", "expected_crisis": False, "category": "Metaphor/Idiom"},
    {"text": "My feet are killing me after walking all day.", "expected_crisis": False, "category": "Metaphor/Idiom"},
    {"text": "I made a killer presentation today at work.", "expected_crisis": False, "category": "Metaphor/Idiom"},
    
    # 3. Explicit High-Risk Crisis Signals
    {"text": "I feel so overwhelmed and hopeless. I don't want to wake up tomorrow.", "expected_crisis": True, "category": "Explicit Crisis"},
    {"text": "Everything is hurting me and I can't take this pain anymore. I want to end my life.", "expected_crisis": True, "category": "Explicit Crisis"},
    {"text": "I am planning to kill myself tonight with pills.", "expected_crisis": True, "category": "Explicit Crisis"},
    {"text": "Goodbye everyone, this is my final message.", "expected_crisis": True, "category": "Explicit Crisis"},
    {"text": "I am going to cut my wrists, I can't live like this.", "expected_crisis": True, "category": "Explicit Crisis"},
    
    # 4. Subtle Distress & Ambiguous Statements
    {"text": "I just feel completely empty and exhausted with life.", "expected_crisis": False, "category": "Subtle Distress"},
    {"text": "What is the point of working so hard when nothing changes?", "expected_crisis": False, "category": "Subtle Distress"},
    {"text": "Sometimes I wonder what happens after people die.", "expected_crisis": False, "category": "Subtle Distress"},
    {"text": "I feel so alone and nobody seems to care about me.", "expected_crisis": False, "category": "Subtle Distress"},
]


def run_stress_test(max_dataset_samples: int = 1000):
    print("=================================================================")
    print("     MINDGUARD 1,000+ EDGE-CASE BENCHMARK & STRESS TEST          ")
    print("=================================================================")
    
    print("\n1. Loading HuggingFace ML Models into Memory...")
    start_load = time.time()
    load_ml_pipelines()
    print(f" -> ML Engines Loaded in {time.time() - start_load:.2f}s")
    
    # Load dataset test samples
    dataset_candidates = [
        PROJECT_ROOT / "tests" / "data" / "crisis_test_utterances.csv",
        PROJECT_ROOT / "tests" / "data" / "crisis_independent_eval_dataset.csv",
    ]
    dataset_path = next((p for p in dataset_candidates if p.exists()), None)
    if dataset_path is None:
        print("[!] Dataset test file not found in expected locations:")
        for p in dataset_candidates:
            print(f"    - {p}")
        sys.exit(1)
        
    print(f"\n2. Loading Test Dataset from {dataset_path.name}...")
    df = pd.read_csv(dataset_path)
    # Take balanced sample up to max_dataset_samples
    suicide_df = df[df["label"] == "suicide"].head(max_dataset_samples // 2)
    non_suicide_df = df[df["label"] == "non_suicide"].head(max_dataset_samples // 2)
    
    combined_samples = []
    
    # Add synthetic edge cases first
    for item in SYNTHETIC_EDGE_CASES:
        combined_samples.append({
            "text": item["text"],
            "expected_crisis": item["expected_crisis"],
            "source": f"synthetic_{item['category']}"
        })
        
    # Add dataset samples
    for _, row in suicide_df.iterrows():
        combined_samples.append({
            "text": str(row["text"]),
            "expected_crisis": True,
            "source": "dataset_crisis"
        })
    for _, row in non_suicide_df.iterrows():
        combined_samples.append({
            "text": str(row["text"]),
            "expected_crisis": False,
            "source": "dataset_non_crisis"
        })
        
    total_samples = len(combined_samples)
    print(f" -> Total Benchmark Samples: {total_samples} (Synthetic: {len(SYNTHETIC_EDGE_CASES)}, Dataset: {len(suicide_df) + len(non_suicide_df)})")
    
    print("\n3. Running Pipeline Evaluation across all samples...")
    tp, fp, tn, fn = 0, 0, 0, 0
    latencies = []
    failed_cases = []
    
    start_eval = time.time()
    
    for i, sample in enumerate(combined_samples):
        text = sample["text"]
        expected = sample["expected_crisis"]
        
        t0 = time.time()
        
        # Step A: Deterministic Rule Check
        det_result = evaluate_deterministic_crisis(text)
        is_crisis = False
        decision_source = "deterministic_rule"
        
        if det_result["is_crisis"]:
            is_crisis = True
        else:
            # Step B: Zero-Shot ML Classification if not caught by rules
            ml_result = analyze_user_message(text)
            intent = ml_result.get("intent", "")
            intent_conf = ml_result.get("intent_confidence", 0.0)
            
            if intent == "SUICIDE CRISIS OR SELF HARM RISK" and intent_conf > 0.40 and not is_contextual_or_negated(text):
                is_crisis = True
                decision_source = f"zero_shot_ml ({intent_conf:.2f})"
            else:
                decision_source = "safe_or_low_risk"
                
        latency = (time.time() - t0) * 1000
        latencies.append(latency)
        
        # Confusion Matrix updates
        if expected and is_crisis:
            tp += 1
        elif not expected and not is_crisis:
            tn += 1
        elif not expected and is_crisis:
            fp += 1
            failed_cases.append({"text": text, "expected": expected, "predicted": is_crisis, "source": sample["source"], "type": "False Positive", "decision": decision_source})
        elif expected and not is_crisis:
            fn += 1
            failed_cases.append({"text": text, "expected": expected, "predicted": is_crisis, "source": sample["source"], "type": "False Negative", "decision": decision_source})
            
        if (i + 1) % 200 == 0 or (i + 1) == total_samples:
            print(f" -> Processed {i + 1}/{total_samples} cases...")
            
    total_eval_time = time.time() - start_eval
    
    # Calculate performance metrics
    accuracy = (tp + tn) / total_samples if total_samples > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    
    print("\n=================================================================")
    print("                 BENCHMARK PERFORMANCE RESULTS                   ")
    print("=================================================================")
    print(f" Total Samples Evaluated : {total_samples}")
    print(f" True Positives (TP)     : {tp}")
    print(f" True Negatives (TN)     : {tn}")
    print(f" False Positives (FP)    : {fp}")
    print(f" False Negatives (FN)    : {fn}")
    print("-----------------------------------------------------------------")
    print(f" Accuracy                : {accuracy * 100:.2f}%")
    print(f" Precision               : {precision * 100:.2f}%")
    print(f" Recall (Sensitivity)    : {recall * 100:.2f}%")
    print(f" F1-Score                : {f1_score * 100:.2f}%")
    print(f" Average Latency / req   : {avg_latency:.2f} ms")
    print(f" Total Evaluation Time   : {total_eval_time:.2f} s")
    print("=================================================================")
    
    # Save benchmark artifacts
    artifacts_dir = PROJECT_ROOT / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    report_file = artifacts_dir / "stress_test_1000_report.json"
    
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "metrics": {
                "total_samples": total_samples,
                "accuracy": round(accuracy, 4),
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1_score": round(f1_score, 4),
                "avg_latency_ms": round(avg_latency, 2),
                "false_positives": fp,
                "false_negatives": fn
            },
            "failures": failed_cases
        }, f, indent=2)
        
    print(f"\n[INFO] Detailed JSON report saved to: {report_file}")


if __name__ == "__main__":
    run_stress_test()
