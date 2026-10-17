"""
tests/backend/test_roman_urdu_sealed_integrity.py
==================================================
Hygiene test enforcing cryptographic integrity of the sealed Roman Urdu benchmark.
Fails if roman_urdu_crisis_benchmark_sealed_100.json is modified, corrupted, or tampered with.
"""

import hashlib
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SEALED_PATH = ROOT / "tests" / "data" / "roman_urdu_crisis_benchmark_sealed_100.json"

# Cryptographic SHA-256 digest of the pristine 100-case sealed benchmark
EXPECTED_SEALED_SHA256 = "0fcd3fdb276a8b528cb639444ba84aab389e36310c3e1aa597b77eb93890eae3"


def test_sealed_benchmark_exists_and_unaltered():
    """Asserts that the sealed Roman Urdu test set exists and matches its exact SHA-256 digest."""
    assert SEALED_PATH.is_file(), f"Sealed benchmark missing at {SEALED_PATH}"

    file_bytes = SEALED_PATH.read_bytes()
    computed_sha256 = hashlib.sha256(file_bytes).hexdigest()

    assert computed_sha256 == EXPECTED_SEALED_SHA256, (
        f"SEALED BENCHMARK INTEGRITY VIOLATION!\n"
        f"The sealed holdout benchmark has been modified or corrupted.\n"
        f"Expected SHA-256: {EXPECTED_SEALED_SHA256}\n"
        f"Computed SHA-256: {computed_sha256}"
    )


def test_sealed_benchmark_sample_count():
    """Asserts that the sealed benchmark contains exactly 100 samples with 50 crisis and 50 benign."""
    import json
    with open(SEALED_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)

    assert len(cases) == 100, f"Expected 100 cases, found {len(cases)}"
    crisis_cases = [c for c in cases if c.get("expected_crisis")]
    benign_cases = [c for c in cases if not c.get("expected_crisis")]

    assert len(crisis_cases) == 50, f"Expected 50 crisis cases, found {len(crisis_cases)}"
    assert len(benign_cases) == 50, f"Expected 50 benign cases, found {len(benign_cases)}"
