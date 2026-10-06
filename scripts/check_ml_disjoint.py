"""Fail if the ML training/eval data overlaps benchmark skeletons (DEV or TEST)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def norm(t):
    return re.sub(r"\s+", " ", t.lower()).strip()

def main():
    texts, skel_norms = set(), set()
    for f in ["tests/data/roman_urdu_benchmark.json", "tests/data/roman_urdu_adversarial.json"]:
        for c in json.loads((ROOT / f).read_text(encoding="utf-8"))["cases"]:
            skel_norms.add(norm(c["text"]))
    ml = (ROOT / "ml" / "data" / "roman_urdu_augmented.csv")
    if not ml.exists():
        print("SKIP: ml/data/roman_urdu_augmented.csv not generated yet")
        return
    import csv
    with open(ml, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            texts.add(norm(row["text"]))
    overlap = texts & skel_norms
    print(f"ML rows {len(texts)} | benchmark cases {len(skel_norms)} | overlap {len(overlap)}")
    if overlap:
        for t in list(overlap)[:10]:
            print("  OVERLAP:", t)
        sys.exit(1)
    print("DISJOINT: PASS")

if __name__ == "__main__":
    main()
