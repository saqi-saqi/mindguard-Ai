"""
Split the Roman Urdu benchmark into DEV (60%) and TEST (40%), grouped by
skeleton so no skeleton's variants straddle the split.

TEST is frozen: tests/data/holdout/roman_urdu_test_frozen.json + SHA-256
logged in artifacts/test_runs.json + folder set read-only (Windows).

HARNESS-ONLY ACCESS RULE: after this script runs, the TEST file is read ONLY
by scripts/eval_roman_urdu_holdout.py, which prints aggregate metrics and
failing IDs — never case text. All tuning happens against DEV.
"""
import hashlib
import json
import random
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tests" / "data" / "roman_urdu_benchmark.json"
DEV_OUT = ROOT / "tests" / "data" / "roman_urdu_benchmark_dev.json"
HOLDOUT_DIR = ROOT / "tests" / "data" / "holdout"
TEST_OUT = HOLDOUT_DIR / "roman_urdu_test_frozen.json"
RUNS_LOG = ROOT / "artifacts" / "test_runs.json"
SEED = 42
DEV_SHARE = 0.6
MIN_TEST_SKELETONS_T1_T2 = 8

T12 = {"means_attempt", "imminent_intent", "explicit_intent", "burden_goodbye", "self_harm"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def log_run(entry: dict):
    log = json.loads(RUNS_LOG.read_text(encoding="utf-8")) if RUNS_LOG.exists() else {"entries": []}
    log["entries"].append(entry)
    RUNS_LOG.write_text(json.dumps(log, indent=1), encoding="utf-8")


def set_readonly(path: Path):
    if sys.platform == "win32":
        subprocess.run(["attrib", "+R", str(path)], check=False)
    else:
        path.chmod(0o444)


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    cases = data["cases"]

    by_cat = defaultdict(lambda: defaultdict(list))  # category -> skeleton_id -> cases
    for c in cases:
        by_cat[c["category"]][c["skeleton_id"]].append(c)

    rng = random.Random(SEED)
    dev, test = [], []
    report = {}
    for cat, skels in sorted(by_cat.items()):
        ids = sorted(skels.keys())
        rng.shuffle(ids)
        n = len(ids)
        n_test = max(MIN_TEST_SKELETONS_T1_T2, round(n * (1 - DEV_SHARE))) if cat in T12 else round(n * (1 - DEV_SHARE))
        n_test = min(n_test, n - 1)  # keep at least 1 skeleton in DEV
        test_ids = set(ids[:n_test])
        c_dev = [c for sid in ids if sid not in test_ids for c in skels[sid]]
        c_test = [c for sid in ids if sid in test_ids for c in skels[sid]]
        dev.extend(c_dev)
        test.extend(c_test)
        t12_flag = " (T1/T2 gate: >=8)" if cat in T12 else ""
        report[cat] = {
            "skeletons_total": n, "skeletons_dev": n - n_test, "skeletons_test": n_test,
            "cases_dev": len(c_dev), "cases_test": len(c_test), "gate_ok": (n_test >= 8) if cat in T12 else None,
        }
        print(f"{cat:26s} skeletons {n:3d} -> dev {n - n_test:3d} / test {n_test:2d} | cases {len(c_dev):3d}/{len(c_test):3d}{t12_flag}")

    gate_fail = [c for c, r in report.items() if r["gate_ok"] is False]
    print(f"\nDEV: {len(dev)} cases | TEST: {len(test)} cases | balance gate failures: {gate_fail or 'none'}")
    if gate_fail:
        print("STAGE 1 BALANCE GATE FAILED")
        sys.exit(1)

    DEV_OUT.write_text(json.dumps({"meta": {"split": "dev", "seed": SEED}, "cases": dev}, ensure_ascii=False, indent=1), encoding="utf-8")
    HOLDOUT_DIR.mkdir(parents=True, exist_ok=True)
    TEST_OUT.write_text(json.dumps({"meta": {"split": "test_frozen", "seed": SEED,
        "access": "harness-only: scripts/eval_roman_urdu_holdout.py"}, "cases": test}, ensure_ascii=False, indent=1), encoding="utf-8")
    set_readonly(TEST_OUT)

    log_run({"type": "freeze", "timestamp": datetime.now(timezone.utc).isoformat(),
             "dev_cases": len(dev), "test_cases": len(test),
             "test_sha256": sha256(TEST_OUT), "corpus_sha256": sha256(SRC)})
    (ROOT / "artifacts" / "split_report.json").write_text(json.dumps({
        "seed": SEED, "dev_cases": len(dev), "test_cases": len(test),
        "test_sha256": sha256(TEST_OUT), "per_category": report}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nfrozen TEST: {TEST_OUT}")
    print(f"  sha256: {sha256(TEST_OUT)}")
    print(f"  runs log: {RUNS_LOG} (freeze entry written; folder set read-only)")


if __name__ == "__main__":
    main()
