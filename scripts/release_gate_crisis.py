import csv
import json
import sys
from pathlib import Path

# Fix Windows console UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
SERVER_DIR = ROOT_DIR / "server"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from services.crisis_rules import evaluate_deterministic_crisis
from services.calibration_monitor import run_calibration_audit


def run_evaluation(csv_file_path: Path):
    total = 0
    tp = fp = tn = fn = 0
    
    # Sub-category metrics tracking
    subcat_stats = {
        "explicit_intent": {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "is_crisis_cat": True},
        "indirect_distress": {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "is_crisis_cat": True},
        "burden_goodbye": {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "is_crisis_cat": True},
        "lethal_preparation": {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "is_crisis_cat": True},
        "subtle_slang": {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "is_crisis_cat": True},
        "self_harm": {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "is_crisis_cat": True},
        "active_escalation": {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "is_crisis_cat": True},
        "negation": {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "is_crisis_cat": False},
        "past_historical": {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "is_crisis_cat": False},
        "academic_media": {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "is_crisis_cat": False},
        "idiom_hyperbole": {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "is_crisis_cat": False},
    }

    with open(csv_file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            text = row['text']
            cat = row['category']
            severity = int(row['severity'])
            
            is_actual_crisis = (severity >= 3) and (cat not in ['idiom_non_crisis', 'negation_past_academic'])
            
            res = evaluate_deterministic_crisis(text)
            pred_crisis = res['is_crisis']
            
            # Map category to subcat_stats key
            sub_key = "other"
            if cat == "idiom_non_crisis":
                sub_key = "idiom_hyperbole"
            elif cat == "negation_past_academic":
                text_lower = text.lower()
                if any(w in text_lower for w in ["used to", "5 years ago", "4 years ago", "past", "recovered"]):
                    sub_key = "past_historical"
                elif any(w in text_lower for w in ["thesis", "exam", "documentary", "movie", "book", "class", "study", "guidelines"]):
                    sub_key = "academic_media"
                else:
                    sub_key = "negation"
            elif cat in subcat_stats:
                sub_key = cat
            elif cat in ["self_harm_cutting"]:
                sub_key = "self_harm"

            if pred_crisis and is_actual_crisis:
                tp += 1
                if sub_key in subcat_stats: subcat_stats[sub_key]["tp"] += 1
            elif pred_crisis and not is_actual_crisis:
                fp += 1
                if sub_key in subcat_stats: subcat_stats[sub_key]["fp"] += 1
            elif not pred_crisis and not is_actual_crisis:
                tn += 1
                if sub_key in subcat_stats: subcat_stats[sub_key]["tn"] += 1
            elif not pred_crisis and is_actual_crisis:
                fn += 1
                if sub_key in subcat_stats: subcat_stats[sub_key]["fn"] += 1

    acc = (tp + tn) / total if total else 0
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
    fnr = fn / (tp + fn) if (tp + fn) else 0
    fpr = fp / (fp + tn) if (fp + tn) else 0

    return {
        "total": total,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "fnr": fnr,
        "fpr": fpr,
        "subcat_stats": subcat_stats
    }


def run_aggressive_suite():
    """Runs the full aggressive crisis rules test suite from test_crisis_engine.py."""
    tests_dir = Path(__file__).resolve().parent.parent / "tests" / "backend"
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))
    try:
        from test_safety_and_crisis_engine import all_aggressive_cases as all_cases
        passed = 0
        total = 0
        for cat, labelled_text, expected in all_cases():
            total += 1
            text = labelled_text.split(": ", 1)[-1] if labelled_text.startswith("variant_") else labelled_text
            res = evaluate_deterministic_crisis(text)
            if res["is_crisis"] == expected:
                passed += 1
        return passed, total
    except Exception as e:
        print(f"    [ERROR] Failed to run aggressive test suite: {e}")
        return 0, 0


def main():
    print("=" * 85)
    print("        MINDGUARD TIER-1 CRISIS DETECTION CI RELEASE GATE & VERIFICATION")
    print("=" * 85)
    
    root_dir = Path(__file__).resolve().parent.parent
    dev_csv = root_dir / "tests" / "data" / "crisis_test_utterances.csv"
    eval_csv = root_dir / "tests" / "data" / "crisis_independent_eval_dataset.csv"
    fixture_json = root_dir / "tests" / "fixtures" / "crisis_regression_cases.json"

    # 1. Evaluate Versioned Regression Fixture
    print("\n[1] Evaluating Versioned Regression Fixture (tests/fixtures/crisis_regression_cases.json)")
    fixture_total = 0
    fixture_passed = 0
    if fixture_json.exists():
        with open(fixture_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
            cases = data.get("cases", [])
            fixture_total = len(cases)
            for c in cases:
                res = evaluate_deterministic_crisis(c["text"])
                if res["is_crisis"] == c["expected_is_crisis"]:
                    fixture_passed += 1
            print(f"    Regression Fixture Result: {fixture_passed}/{fixture_total} Passed ({fixture_passed/fixture_total*100:.1f}%)")
    else:
        print("    [WARN] Regression fixture file not found.")

    fixture_gate_pass = (fixture_passed == fixture_total) and (fixture_total > 0)

    # 2. Evaluate Aggressive Crisis Rule Suite
    print("\n[2] Evaluating Aggressive Crisis Rule Suite")
    agg_passed, agg_total = run_aggressive_suite()
    agg_gate_pass = (agg_passed == agg_total)
    print(f"    Aggressive Rule Suite Result: {agg_passed}/{agg_total} Passed ({agg_passed/agg_total*100:.1f}%)")

    # 3. Evaluate Development Benchmark
    print("\n[3] Evaluating Development Benchmark (extras/dataset/crisis_test_utterances.csv - 530 Cases)")
    dev_res = run_evaluation(dev_csv)
    print(f"    TP: {dev_res['tp']}, FP: {dev_res['fp']}, TN: {dev_res['tn']}, FN: {dev_res['fn']}")
    print(f"    Accuracy:             {dev_res['accuracy']*100:.2f}%")
    print(f"    Precision:            {dev_res['precision']*100:.2f}%")
    print(f"    Recall (Sensitivity): {dev_res['recall']*100:.2f}%")
    print(f"    F1-Score:             {dev_res['f1']*100:.2f}%")
    print(f"    False Negative Rate:  {dev_res['fnr']*100:.2f}%")
    print(f"    False Positive Rate:  {dev_res['fpr']*100:.2f}%")

    # 4. Evaluate Locked Independent Evaluation Dataset
    print("\n[4] Evaluating Locked Independent Evaluation Dataset (extras/dataset/crisis_independent_eval_dataset.csv - 100 Cases)")
    eval_res = run_evaluation(eval_csv)
    print(f"    TP: {eval_res['tp']}, FP: {eval_res['fp']}, TN: {eval_res['tn']}, FN: {eval_res['fn']}")
    print(f"    Accuracy:             {eval_res['accuracy']*100:.2f}%")
    print(f"    Precision:            {eval_res['precision']*100:.2f}%")
    print(f"    Recall (Sensitivity): {eval_res['recall']*100:.2f}%")
    print(f"    F1-Score:             {eval_res['f1']*100:.2f}%")
    print(f"    False Negative Rate:  {eval_res['fnr']*100:.2f}%")
    print(f"    False Positive Rate:  {eval_res['fpr']*100:.2f}%")

    print("\n[Sub-Category Breakdown on Independent Evaluation Dataset]:")
    for key, s in eval_res["subcat_stats"].items():
        sub_total = s["tp"] + s["fp"] + s["tn"] + s["fn"]
        if sub_total > 0:
            if s["is_crisis_cat"]:
                sub_rec = (s["tp"] / (s["tp"] + s["fn"])) * 100 if (s["tp"] + s["fn"]) > 0 else 100.0
                sub_prec = (s["tp"] / (s["tp"] + s["fp"])) * 100 if (s["tp"] + s["fp"]) > 0 else 100.0
                print(f"    - {key:20s} [CRISIS]:     Count={sub_total:2d} | TP={s['tp']:2d}, FN={s['fn']:2d} | Recall={sub_rec:5.1f}%, Precision={sub_prec:5.1f}%")
            else:
                sub_spec = (s["tn"] / (s["tn"] + s["fp"])) * 100 if (s["tn"] + s["fp"]) > 0 else 100.0
                sub_fpr = (s["fp"] / (s["tn"] + s["fp"])) * 100 if (s["tn"] + s["fp"]) > 0 else 0.0
                print(f"    - {key:20s} [NON-CRISIS]: Count={sub_total:2d} | TN={s['tn']:2d}, FP={s['fp']:2d} | Specificity={sub_spec:5.1f}%, FPR={sub_fpr:5.1f}%")

    # 5. Run Adversarial Calibration & Invariant Audit
    print("\n[5] Running Adversarial Calibration & Invariant Audit (services.calibration_monitor)")
    calib_res = run_calibration_audit()
    print(f"    Cases: {calib_res['total_cases']} | Accuracy: {calib_res['accuracy']*100:.2f}% | Sensitivity: {calib_res['sensitivity']*100:.2f}% | Specificity: {calib_res['specificity']*100:.2f}%")
    print(f"    Tier 1 Critical Bypasses: {calib_res['tier_1_bypasses']}")

    # 6. Check Release Gate Status Assertions
    print("\n" + "=" * 85)
    print("                     RELEASE GATE STATUS ASSERTIONS & CHECKS                     ")
    print("=" * 85)
    
    rec_pass = eval_res["recall"] >= 0.95
    fnr_pass = eval_res["fnr"] <= 0.05
    prec_pass = eval_res["precision"] >= 0.90
    fpr_pass = eval_res["fpr"] <= 0.05
    calib_pass = calib_res["passed_invariants"] and (calib_res["tier_1_bypasses"] == 0)

    print(f"  Holdout Recall >= 95.0%        : {'[PASS]' if rec_pass else '[FAIL]'} ({eval_res['recall']*100:.2f}%)")
    print(f"  Holdout False-Negative Rate <= 5%: {'[PASS]' if fnr_pass else '[FAIL]'} ({eval_res['fnr']*100:.2f}%)")
    print(f"  Holdout Precision >= 90.0%     : {'[PASS]' if prec_pass else '[FAIL]'} ({eval_res['precision']*100:.2f}%)")
    print(f"  Holdout False-Positive Rate <= 5%: {'[PASS]' if fpr_pass else '[FAIL]'} ({eval_res['fpr']*100:.2f}%)")
    print(f"  Regression Fixture Pass Rate=100%: {'[PASS]' if fixture_gate_pass else '[FAIL]'} ({fixture_passed}/{fixture_total})")
    print(f"  Aggressive Suite Pass Rate=100% : {'[PASS]' if agg_gate_pass else '[FAIL]'} ({agg_passed}/{agg_total})")
    print(f"  Adversarial Calibration Gate   : {'[PASS]' if calib_pass else '[FAIL]'} (Sensitivity={calib_res['sensitivity']*100:.1f}%, Bypasses={calib_res['tier_1_bypasses']})")

    print("\nNote: Tier-1 Deterministic Rule Engine metrics are evaluated above.")
    print("      Tier-2 ML Classifier metrics are tracked separately and do NOT validate Tier 1.")

    all_passed = rec_pass and fnr_pass and prec_pass and fpr_pass and fixture_gate_pass and agg_gate_pass and calib_pass

    print("=" * 85)
    if all_passed:
        print("  RELEASE GATE VERIFICATION: SUCCESSFUL [PASS]")
        print("=" * 85 + "\n")
        sys.exit(0)
    else:
        print("  RELEASE GATE VERIFICATION: FAILED REQUIREMENTS [FAIL]")
        print("=" * 85 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
