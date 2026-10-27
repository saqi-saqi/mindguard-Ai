"""
benchmark_crisis_latency.py
===========================
High-resolution empirical benchmarking harness for MindGuard Tier 1 Crisis Triage.
Compares:
1. Legacy Dual Pipeline (classify_safety_risk + evaluate_crisis_pipeline)
2. Unified Single Pipeline (evaluate_unified_tier1_safety)

Measures real wall-clock latency (mean, median, min, max, p95, stdev) and calculates
the exact empirical latency delta and percentage savings.
"""

from __future__ import annotations

import os
import sys
import time
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

os.environ.setdefault("USE_MONGOMOCK", "true")
os.environ.setdefault("FLASK_ENV", "testing")

from services.safety_classifier import classify_safety_risk
from services.crisis_rules import evaluate_crisis_pipeline
from services.unified_safety_pipeline import evaluate_unified_tier1_safety

TEST_CORPUS = [
    ("TP-01 Acute Self-Harm", "I want to kill myself tonight, I have pills ready"),
    ("TP-02 Harm to Others", "I'm going to kill my coworker tonight with a kitchen knife"),
    ("TP-03 Combined Crisis", "I will murder him and after that next on my killing list is me"),
    ("TP-05 Third-Party Report", "Atif wants to kill Taimoor tonight"),
    ("TP-08 Idiom / Slang", "This exam is literally killing me lol"),
    ("TP-09 Negation", "I don't want to die, I want to get better and live"),
    ("TP-10 Past Recovery", "I used to self-harm 3 years ago, but I have been clean and happy now"),
    ("TP-11 Emotional Distress", "I am feeling so overwhelmed, hopeless, exhausted, and heartbroken today"),
    ("TP-12 Casual Benign", "Hello, can you help me organize my study schedule?"),
    ("Multi-Sentence Complex", "I had a really difficult meeting today with my supervisor. We were discussing my thesis progress and how much research is remaining. Sometimes it feels like this work is never-ending, but I want to take a breath and figure out the next steps for my paper."),
]


def run_legacy_tier1(text: str, context_turns=None, session_id=None):
    """Executes the exact legacy dual-pipeline from app.py lines 944-954."""
    t0 = time.perf_counter_ns()
    safety_eval = classify_safety_risk(
        text,
        context_turns=context_turns,
        session_id=session_id
    )
    crisis_eval = evaluate_crisis_pipeline(
        text,
        allow_ml_fallback=False,
        context_turns=context_turns
    )
    t1 = time.perf_counter_ns()
    return (t1 - t0) / 1_000_000.0, safety_eval, crisis_eval


def run_unified_tier1(text: str, context_turns=None, session_id=None):
    """Executes the unified single-pass pipeline."""
    t0 = time.perf_counter_ns()
    res = evaluate_unified_tier1_safety(
        text,
        context_turns=context_turns,
        session_id=session_id
    )
    t1 = time.perf_counter_ns()
    return (t1 - t0) / 1_000_000.0, res, res


def benchmark_pipeline(runner_fn, iterations=100, warmup=15):
    results = {}
    
    # Warmup
    for _, text in TEST_CORPUS:
        for _ in range(warmup):
            runner_fn(text)

    # Measurement
    for label, text in TEST_CORPUS:
        times_ms = []
        for _ in range(iterations):
            dur_ms, _, _ = runner_fn(text)
            times_ms.append(dur_ms)
        
        times_ms.sort()
        p95_idx = int(len(times_ms) * 0.95)
        results[label] = {
            "mean": statistics.mean(times_ms),
            "median": statistics.median(times_ms),
            "min": min(times_ms),
            "max": max(times_ms),
            "p95": times_ms[p95_idx],
            "stdev": statistics.stdev(times_ms) if len(times_ms) > 1 else 0.0,
            "raw": times_ms
        }
    return results


def print_comparison_table(legacy_res: dict, unified_res: dict):
    print(f"\n{'='*105}")
    print(f"{'EMPIRICAL BENCHMARK: LEGACY DUAL PIPELINE vs UNIFIED SINGLE PIPELINE':^105}")
    print(f"{'='*105}")
    header = f"{'Scenario':<25} | {'Legacy Mean':<12} | {'Unified Mean':<12} | {'Saving (ms)':<12} | {'% Speedup':<10} | {'p95 Leg':<8} | {'p95 Uni':<8}"
    print(header)
    print(f"{'-'*25}-+-{'-'*12}-+-{'-'*12}-+-{'-'*12}-+-{'-'*10}-+-{'-'*8}-+-{'-'*8}")
    
    legacy_means = []
    unified_means = []

    for label in legacy_res:
        leg_m = legacy_res[label]["mean"]
        uni_m = unified_res[label]["mean"]
        diff_ms = leg_m - uni_m
        pct = (diff_ms / leg_m) * 100.0 if leg_m > 0 else 0.0
        
        legacy_means.append(leg_m)
        unified_means.append(uni_m)
        
        leg_p95 = legacy_res[label]["p95"]
        uni_p95 = unified_res[label]["p95"]
        
        print(f"{label:<25} | {leg_m:>10.3f} ms | {uni_m:>10.3f} ms | {diff_ms:>10.3f} ms | {pct:>8.1f} % | {leg_p95:>6.2f} ms | {uni_p95:>6.2f} ms")
    
    tot_leg = statistics.mean(legacy_means)
    tot_uni = statistics.mean(unified_means)
    tot_diff = tot_leg - tot_uni
    tot_pct = (tot_diff / tot_leg) * 100.0

    print(f"{'-'*25}-+-{'-'*12}-+-{'-'*12}-+-{'-'*12}-+-{'-'*10}-+-{'-'*8}-+-{'-'*8}")
    print(f"{'OVERALL AVERAGE':<25} | {tot_leg:>10.3f} ms | {tot_uni:>10.3f} ms | {tot_diff:>10.3f} ms | {tot_pct:>8.1f} % |")
    print(f"{'='*105}\n")
    return tot_leg, tot_uni, tot_pct


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()

    print(f"Running high-resolution benchmark with {args.iterations} iterations per test scenario...")
    print("1. Benchmarking Legacy Dual Pipeline...")
    legacy_results = benchmark_pipeline(run_legacy_tier1, iterations=args.iterations)

    print("2. Benchmarking Unified Single Pipeline...")
    unified_results = benchmark_pipeline(run_unified_tier1, iterations=args.iterations)

    print_comparison_table(legacy_results, unified_results)
