"""
scripts/benchmarks/test_guardrail_on_failures.py
-------------------------------------------------
Evaluates the remaining 20 failure cases from edge_case_evaluation_report.json
using the Tier-2.5 LLM Clinical Guardrail to test if the LLM catches them.
"""

import sys
import json
import time
from pathlib import Path

# Fix console encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from services.llm_service import evaluate_llm_safety_guardrail

REPORT_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "edge_case_evaluation_report.json"

if not REPORT_PATH.exists():
    print(f"[ERROR] Evaluation report not found at: {REPORT_PATH}")
    sys.exit(1)

with open(REPORT_PATH, "r", encoding="utf-8") as f:
    report = json.load(f)

failures = [r for r in report["results"] if r["status"].startswith("FAIL")]
print("=================================================================")
print(f"  EVALUATING TIER 2.5 LLM GUARDRAIL ON {len(failures)} REMAINING FAILURES")
print("=================================================================\n")

guardrail_fixed = 0
guardrail_failed = 0
results = []

for idx, f in enumerate(failures, 1):
    text = f["text"]
    expected = f["expected_crisis"]
    category = f["category"]
    old_status = f["status"]

    print(f"[{idx}/{len(failures)}] Testing: \"{text}\"")
    print(f"  • Category        : {category}")
    print(f"  • Expected Crisis : {expected}")
    print(f"  • Old ML Failure  : {old_status} ({f['method']})")

    start_t = time.time()
    guardrail_res = evaluate_llm_safety_guardrail(text)
    latency = time.time() - start_t

    if guardrail_res is None:
        print("  -> Guardrail returned None (API error or timeout)")
        guardrail_failed += 1
        continue

    predicted = guardrail_res["is_crisis"]
    conf = guardrail_res.get("confidence", 0.0)
    reasoning = guardrail_res.get("reasoning", "")

    is_correct = (predicted == expected)
    if is_correct:
        guardrail_fixed += 1
        verdict = "FIXED BY GUARDRAIL ✅"
    else:
        guardrail_failed += 1
        verdict = "STILL FAILED ❌"

    print(f"  • LLM Predicted   : {predicted} (Confidence: {conf:.2f}, Latency: {latency:.2f}s)")
    print(f"  • LLM Reasoning   : \"{reasoning}\"")
    print(f"  • Result          : {verdict}\n")

print("=================================================================")
print("                    LLM GUARDRAIL EVALUATION SUMMARY             ")
print("=================================================================")
print(f" Total Hard Failure Cases Tested: {len(failures)}")
print(f" Successfully Fixed by Guardrail: {guardrail_fixed} / {len(failures)} ({guardrail_fixed/len(failures)*100:.1f}%)")
print(f" Still Failed                   : {guardrail_failed}")
print("=================================================================")
