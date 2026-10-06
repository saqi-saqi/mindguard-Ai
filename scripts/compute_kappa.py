"""
Compute inter-reviewer agreement (Cohen's kappa) from returned reviewer sheets.

Usage:
  python scripts/compute_kappa.py artifacts/reviewer_sheets/returned/pilot_reviewer_1.csv \
      artifacts/reviewer_sheets/returned/pilot_reviewer_2.csv [more.csv ...]

- Sheets must share case_id columns (pilot/dev sheets are the same cases for all
  reviewers, so kappa is pairwise on identical case sets).
- Reports overall kappa + per-cohort kappa + disagreement list.
- Cases where ANY reviewer said "unsure" go to needs_adjudication (owner decides,
  blind: labels only, never rule output). Marked adjudicator=owner.
- Exit code 0 if pairwise kappa >= 0.60 (pilot gate), else 1.
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
RUNS_LOG = ROOT / "artifacts" / "test_runs.json"
CORPUS = ROOT / "tests" / "data" / "roman_urdu_benchmark.json"


def load_sheet(path: Path) -> dict:
    rows = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            cid = (r.get("case_id") or "").strip()
            if not cid or cid.startswith("("):
                continue
            label = None
            for key in r:  # tolerate both long and short header variants
                if key and key.strip().lower().startswith("your_label"):
                    label = (r[key] or "").strip().lower()
                    break
            rows[cid] = label or ""
    return rows


def kappa(a: list, b: list) -> float:
    n = len(a)
    if n == 0:
        return 0.0
    labels = sorted(set(a) | set(b))
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[l] / n) * (cb[l] / n) for l in labels)
    if pe == 1:
        return 1.0 if po == 1 else 0.0
    return (po - pe) / (1 - pe)


def main():
    sheets = [Path(p) for p in sys.argv[1:]]
    if len(sheets) < 2:
        print("need at least 2 returned sheets"); sys.exit(2)
    data = {c["id"]: c for c in json.loads(CORPUS.read_text(encoding="utf-8"))["cases"]}
    labeled = [load_sheet(p) for p in sheets]
    names = [p.stem for p in sheets]

    common = set(labeled[0])
    for s in labeled[1:]:
        common &= set(s)
    common = sorted(common)
    if not common:
        print("no common labeled cases"); sys.exit(2)

    print(f"sheets: {names} | common labeled cases: {len(common)}")
    print("\n== pairwise Cohen's kappa (overall) ==")
    kappas = []
    for i in range(len(labeled)):
        for j in range(i + 1, len(labeled)):
            a = [labeled[i][c] for c in common]
            b = [labeled[j][c] for c in common]
            k = kappa(a, b)
            kappas.append(k)
            print(f"  {names[i]} vs {names[j]}: kappa={k:.3f}")
    min_k = min(kappas)

    # per-cohort kappa (first pair as representative; also min across pairs)
    cohorts = defaultdict(list)
    for cid in common:
        c = data.get(cid)
        cohorts[c["category"] if c else "unknown"].append(cid)
    print("\n== per-cohort kappa (min across pairs) ==")
    per_cohort = {}
    for cat in sorted(cohorts):
        cids = cohorts[cat]
        vals = []
        for i in range(len(labeled)):
            for j in range(i + 1, len(labeled)):
                vals.append(kappa([labeled[i][c] for c in cids], [labeled[j][c] for c in cids]))
        per_cohort[cat] = min(vals)
        print(f"  {cat:26s} n={len(cids):3d} kappa_min={min(vals):.3f}")

    # disagreements / unsure -> adjudication
    adjudicate = []
    for cid in common:
        labels = [s[cid] for s in labeled]
        if "unsure" in labels or len(set(labels)) > 1:
            adjudicate.append({"case_id": cid,
                               "labels": {n: s[cid] for n, s in zip(names, labeled)},
                               "category": data.get(cid, {}).get("category"),
                               "adjudicator": "owner_pending",
                               "note": "decide blind (labels only, never rule output)"})
    print(f"\nneeds_adjudication: {len(adjudicate)} cases (unsure or disagreement)")
    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "sheets": names, "common_cases": len(common),
        "kappa_overall_pairs": {f"{names[i]}|{names[j]}": round(k, 3)
                                 for i in range(len(labeled)) for j in range(i + 1, len(labeled))
                                 for k in [kappa([labeled[i][c] for c in common], [labeled[j][c] for c in common])]},
        "kappa_per_cohort_min": {k: round(v, 3) for k, v in per_cohort.items()},
        "pilot_gate_060": min_k >= 0.60,
        "needs_adjudication": adjudicate,
    }
    outp = ROOT / "artifacts" / "kappa_report.json"
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {outp}")
    print(f"\nPILOT GATE (kappa >= 0.60): {'PASS' if min_k >= 0.60 else 'FAIL — revise guide and re-pilot'}")
    log = json.loads(RUNS_LOG.read_text(encoding="utf-8")) if RUNS_LOG.exists() else {"entries": []}
    log["entries"].append({"type": "kappa_report", "timestamp": out["generated"],
                           "min_pairwise_kappa": round(min_k, 3), "gate_pass": min_k >= 0.60})
    RUNS_LOG.write_text(json.dumps(log, indent=1), encoding="utf-8")
    sys.exit(0 if min_k >= 0.60 else 1)


if __name__ == "__main__":
    main()
