"""
FROZEN-TEST harness — the ONLY code that reads tests/data/holdout/.

Prints AGGREGATE metrics + failing IDs only. Never prints case text.
Verifies the freeze SHA-256 against artifacts/test_runs.json and logs every
run (plan: >3 TEST runs = tuning contamination flag).
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))

TEST = ROOT / "tests" / "data" / "holdout" / "roman_urdu_test_frozen.json"
RUNS = ROOT / "artifacts" / "test_runs.json"

# reuse DEV harness internals
sys.path.insert(0, str(ROOT / "scripts"))
from eval_roman_urdu_dev import run_dataset, tier_metrics, category_style_metrics, wilson  # noqa: E402


def main():
    raw = TEST.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    log = json.loads(RUNS.read_text(encoding="utf-8"))
    freezes = [e for e in log["entries"] if e["type"] == "freeze"]
    test_runs = [e for e in log["entries"] if e["type"] == "test_run"]
    expected = freezes[-1]["test_sha256"] if freezes else None
    if sha != expected:
        print(f"FROZEN HASH MISMATCH: file {sha[:12]} vs logged {str(expected)[:12]} — ABORTING")
        sys.exit(2)
    if len(test_runs) >= 3:
        print(f"CONTAMINATION FLAG: TEST already run {len(test_runs)} times (>=3)")
        sys.exit(2)

    cases = json.loads(raw)["cases"]
    rows = run_dataset(cases, "TEST")
    m = tier_metrics(rows)
    per_cat, per_style = category_style_metrics(rows)

    print("=" * 70)
    print(f"FROZEN TEST EVALUATION — run #{len(test_runs) + 1} | sha256 {sha[:16]}…")
    print(f"n={m['NEG']['negatives'] + sum(m[t]['positives'] for t in ('T1','T2','T3'))} "
          f"(T1 {m['T1']['positives']}, T2 {m['T2']['positives']}, T3 {m['T3']['positives']}, "
          f"NEG {m['NEG']['negatives']})")
    for tier in ("T1", "T2", "T3"):
        t = m[tier]
        print(f"  Tier {tier}: crisis-route recall {t['crisis_route_hits']}/{t['positives']} "
              f"= {t['crisis_route_recall']} (Wilson95 case [{t['wilson95_case'][0]}, {t['wilson95_case'][1]}]; "
              f"skeletons n={t['skeletons']}, conservative {t['skeleton_conservative_recall']}, "
              f"lower bound {t['wilson95_skeleton_lower']}) | any-esc {t['any_escalation_recall']}")
    n = m["NEG"]["negatives"]
    print(f"  NEG: FPR {m['NEG']['false_positives_crisis_route']}/{n} = {m['NEG']['fpr_crisis_route']} "
          f"(CI {m['NEG']['wilson95_fpr']}) | LOW_CONFIDENCE tips {m['NEG']['low_confidence_tips']}")
    print(f"  per-category: {json.dumps(per_cat)}")
    print(f"  per-style: {json.dumps(per_style)}")

    # failing IDs only — never case text
    fn_ids = [r["id"] for r in rows if r["label"] == 1 and not (r["pred_crisis"] or r["pred_guidance"])]
    fp_ids = [r["id"] for r in rows if r["label"] == 0 and r["pred_crisis"]]
    print(f"  failing IDs — FN: {fn_ids or 'none'} | FP: {fp_ids or 'none'}")

    log["entries"].append({
        "type": "test_run", "timestamp": datetime.now(timezone.utc).isoformat(),
        "test_sha256": sha, "metrics": m,
        "failing_ids": {"fn": fn_ids, "fp": fp_ids},
    })
    RUNS.write_text(json.dumps(log, indent=1), encoding="utf-8")
    (ROOT / "artifacts" / "roman_urdu_test_metrics.json").write_text(
        json.dumps({"run": len(test_runs) + 1, "sha256": sha, "metrics": m,
                    "per_category": per_cat, "per_style": per_style,
                    "failing_ids": {"fn": fn_ids, "fp": fp_ids}}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("logged + artifacts/roman_urdu_test_metrics.json written")


if __name__ == "__main__":
    main()
