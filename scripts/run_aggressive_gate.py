"""Re-run the aggressive crisis rule suite against the CURRENT rule engine."""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("USE_MONGOMOCK", "true")
os.environ.setdefault("FLASK_ENV", "testing")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests" / "backend"))

from services.crisis_rules import evaluate_deterministic_crisis  # noqa: E402
from test_safety_and_crisis_engine import all_aggressive_cases  # noqa: E402

total = passed = 0
failures = []
per_cat = {}

for cat, labelled_text, expected in all_aggressive_cases():
    text = labelled_text.split(": ", 1)[-1] if labelled_text.startswith("variant_") else labelled_text
    total += 1
    got = evaluate_deterministic_crisis(text)["is_crisis"]
    s = per_cat.setdefault(cat, {"n": 0, "pass": 0})
    s["n"] += 1
    if got == expected:
        passed += 1
        s["pass"] += 1
    else:
        failures.append({"category": cat, "text": text, "expected": expected, "got": got})

print(f"TOTAL {total} | PASS {passed} | FAIL {total - passed} | rate {passed/total:.4f}")
for cat, s in sorted(per_cat.items()):
    print(f"  {cat:28s} {s['pass']:3d}/{s['n']:3d}")
if failures:
    print("\nFAILURES:")
    for f in failures[:30]:
        print(f"  [{f['category']}] expected={f['expected']} got={f['got']} :: {f['text']}")

report = {
    "total": total, "passed": passed, "failed": total - passed,
    "accuracy": round(passed / total, 4) if total else 0,
    "per_category": per_cat, "failures": failures,
}
(ROOT / "artifacts" / "crisis_rule_aggressive_report.json").write_text(
    json.dumps(report, indent=2), encoding="utf-8")
print("\nreport -> artifacts/crisis_rule_aggressive_report.json")
