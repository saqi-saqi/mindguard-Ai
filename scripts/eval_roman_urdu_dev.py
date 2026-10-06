"""
Roman Urdu evaluation harness (DEV + adversarial + shared metrics).

Route semantics (the "detected" definitions, fixed by the plan):
  - CRISIS ROUTE      : evaluate_crisis_pipeline(...).is_crisis  (recall gates bind here)
  - GUIDANCE ROUTE    : pipeline outcome that is not silence and not the crisis route
                        (third-party guidance, LOW_CONFIDENCE_RISK, script check-in)
  - "any escalation"  : crisis OR guidance route (reported separately; T3 gate binds here)
  - LOW_CONFIDENCE_RISK never counts as a hit for crisis-route recall.

Writes artifacts/roman_urdu_errors.md (FN/FP with reason, 10 hardest grouped
by root cause) and artifacts/roman_urdu_dev_metrics.json. DEV-only: the frozen
TEST file is never opened here.
"""
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))

from server.services.crisis_rules import evaluate_crisis_pipeline  # noqa: E402
from server.services.roman_urdu_router import has_arabic_script  # noqa: E402

DEV = ROOT / "tests" / "data" / "roman_urdu_benchmark_dev.json"
ADVERSARIAL = ROOT / "tests" / "data" / "roman_urdu_adversarial.json"
METRICS_OUT = ROOT / "artifacts" / "roman_urdu_dev_metrics.json"
ERRORS_OUT = ROOT / "artifacts" / "roman_urdu_errors.md"

GUIDANCE_SOURCES = {"third_party_guidance", "low_confidence_checkin"}


def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def eval_case(text: str):
    """Returns (crisis_route, guidance_route, source, reason)."""
    res = evaluate_crisis_pipeline(text, allow_ml_fallback=False)
    crisis = bool(res.get("is_crisis"))
    source = res.get("source", "")
    guidance = (not crisis) and (source in GUIDANCE_SOURCES or res.get("is_third_party")
                                 or res.get("risk_level") == "LOW_CONFIDENCE_RISK"
                                 or res.get("risk_level") == "script_checkin")
    return crisis, guidance, source, res.get("bypass_reason")


def run_dataset(cases, name):
    rows = []
    for c in cases:
        crisis, guidance, source, reason = eval_case(c["text"])
        rows.append({**c, "pred_crisis": crisis, "pred_guidance": guidance,
                     "pred_source": source, "pred_reason": reason})
    return rows


def tier_metrics(rows):
    out = {}
    for tier in ("T1", "T2", "T3"):
        sub = [r for r in rows if r["severity_tier"] == tier]
        pos = [r for r in sub if r["label"] == 1]
        tp = sum(1 for r in pos if r["pred_crisis"])
        any_esc = sum(1 for r in pos if r["pred_crisis"] or r["pred_guidance"])
        n = len(pos)
        lo, hi = wilson(tp, n)
        skels = defaultdict(list)
        for r in pos:
            skels[r["skeleton_id"]].append(r["pred_crisis"] or r["pred_guidance"])
        skel_all = sum(1 for v in skels.values() if all(v))  # conservative cluster hit
        skel_lo, _ = wilson(skel_all, len(skels))
        out[tier] = {
            "positives": n, "crisis_route_hits": tp,
            "crisis_route_recall": round(tp / n, 4) if n else None,
            "wilson95_case": [round(lo, 4), round(hi, 4)],
            "any_escalation_hits": any_esc,
            "any_escalation_recall": round(any_esc / n, 4) if n else None,
            "skeletons": len(skels),
            "skeleton_conservative_hits": skel_all,
            "skeleton_conservative_recall": round(skel_all / len(skels), 4) if skels else None,
            "wilson95_skeleton_lower": round(skel_lo, 4),
        }
    # negatives (FPR on crisis route)
    neg = [r for r in rows if r["label"] == 0]
    fp = sum(1 for r in neg if r["pred_crisis"])
    lo, hi = wilson(fp, len(neg))
    out["NEG"] = {
        "negatives": len(neg), "false_positives_crisis_route": fp,
        "fpr_crisis_route": round(fp / len(neg), 4) if neg else None,
        "wilson95_fpr": [round(lo, 4), round(hi, 4)],
        "low_confidence_tips": sum(1 for r in neg if r["pred_guidance"]),
    }
    return out


def category_style_metrics(rows):
    per_cat, per_style = defaultdict(dict), defaultdict(dict)
    for cat in sorted({r["category"] for r in rows}):
        sub = [r for r in rows if r["category"] == cat]
        tp = sum(1 for r in sub if r["label"] == 1 and r["pred_crisis"])
        esc = sum(1 for r in sub if r["label"] == 1 and (r["pred_crisis"] or r["pred_guidance"]))
        npos = sum(1 for r in sub if r["label"] == 1)
        fp = sum(1 for r in sub if r["label"] == 0 and r["pred_crisis"])
        nneg = sum(1 for r in sub if r["label"] == 0)
        per_cat[cat] = {"n": len(sub), "pos": npos, "tp": tp, "esc": esc, "fp": fp, "neg": nneg}
    for sty in sorted({r["script_style"] for r in rows}):
        sub = [r for r in rows if r["script_style"] == sty]
        tp = sum(1 for r in sub if r["label"] == 1 and r["pred_crisis"])
        npos = sum(1 for r in sub if r["label"] == 1)
        fp = sum(1 for r in sub if r["label"] == 0 and r["pred_crisis"])
        per_style[sty] = {"n": len(sub), "pos": npos, "tp": tp, "fp": fp}
    return per_cat, per_style


def write_errors(rows, label):
    fns = [r for r in rows if r["label"] == 1 and not (r["pred_crisis"] or r["pred_guidance"])]
    fns_soft = [r for r in rows if r["label"] == 1 and r["pred_guidance"] and not r["pred_crisis"]]
    fps = [r for r in rows if r["label"] == 0 and r["pred_crisis"]]
    lines = [f"# Roman Urdu error analysis — {label} ({datetime.now(timezone.utc).isoformat()})", ""]
    lines.append(f"FN (total miss, no escalation): {len(fns)} | FN-soft (guidance-only): {len(fns_soft)} | FP (crisis route on benign): {len(fps)}")
    lines.append("")

    def root_cause(r):
        if r["pred_reason"]:
            return f"guard conflict ({r['pred_reason']})"
        if r["pred_source"] in GUIDANCE_SOURCES:
            return "routed guidance (expected crisis)"
        return "missing pattern"

    lines.append("## 10 hardest FNs (total misses)")
    for r in fns[:10]:
        lines.append(f"- [{r['id']}] ({r['severity_tier']}/{r['category']}/{r['script_style']}) cause={root_cause(r)} :: {r['text']}")
    lines.append("")
    lines.append("## 10 hardest FPs")
    for r in fps[:10]:
        lines.append(f"- [{r['id']}] ({r['category']}/{r['script_style']}) matched={r.get('matched_categories', r['pred_source'])} :: {r['text']}")
    lines.append("")
    lines.append("## All FNs")
    for r in fns:
        lines.append(f"- [{r['id']}] ({r['severity_tier']}/{r['category']}) {root_cause(r)} :: {r['text']}")
    lines.append("")
    lines.append("## All FPs")
    for r in fps:
        lines.append(f"- [{r['id']}] ({r['category']}) :: {r['text']}")
    ERRORS_OUT.write_text("\n".join(lines), encoding="utf-8")
    return len(fns), len(fns_soft), len(fps)


def main():
    dev = json.loads(DEV.read_text(encoding="utf-8"))["cases"]
    adv = json.loads(ADVERSARIAL.read_text(encoding="utf-8"))["cases"]
    print(f"DEV: {len(dev)} cases | adversarial: {len(adv)} cases")

    dev_rows = run_dataset(dev, "DEV")
    adv_rows = run_dataset(adv, "adversarial")
    all_rows = dev_rows + adv_rows

    metrics = {"generated": datetime.now(timezone.utc).isoformat(), "dev": tier_metrics(dev_rows),
               "dev_plus_adversarial": tier_metrics(all_rows)}
    per_cat, per_style = category_style_metrics(all_rows)
    metrics["per_category"] = per_cat
    metrics["per_script_style"] = per_style

    # adversarial ≥95% gate
    adv_ok = sum(1 for r in adv_rows if (r["pred_crisis"] or r["pred_guidance"]) == bool(r["label"]))
    metrics["adversarial"] = {"n": len(adv_rows), "correct": adv_ok,
                              "accuracy": round(adv_ok / len(adv_rows), 4)}
    fn, fns_soft, fp = write_errors(all_rows, "DEV + adversarial")
    print(f"adversarial gate (>=95%): {adv_ok}/{len(adv_rows)} = {adv_ok/len(adv_rows):.1%} -> {'PASS' if adv_ok/len(adv_rows) >= 0.95 else 'FAIL'}")
    for tier in ("T1", "T2", "T3"):
        m = metrics["dev_plus_adversarial"][tier]
        print(f"Tier {tier}: crisis-route {m['crisis_route_hits']}/{m['positives']} "
              f"({m['crisis_route_recall']}) | any-esc {m['any_escalation_hits']}/{m['positives']} "
              f"({m['any_escalation_recall']}) | skeletons {m['skeletons']} cons-recall {m['skeleton_conservative_recall']}")
    m = metrics["dev_plus_adversarial"]["NEG"]
    print(f"NEG: FPR {m['false_positives_crisis_route']}/{m['negatives']} = {m['fpr_crisis_route']} "
          f"(CI {m['wilson95_fpr']}) | LOW_CONFIDENCE tips on benign: {m['low_confidence_tips']}")
    print(f"errors file: {ERRORS_OUT} (FN {fn}, FN-soft {fns_soft}, FP {fp})")
    METRICS_OUT.write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"metrics: {METRICS_OUT}")


if __name__ == "__main__":
    main()
