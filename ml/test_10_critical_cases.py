import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent.parent / "server"
sys.path.insert(0, str(SERVER_DIR))

from services.crisis_rules import evaluate_deterministic_crisis

cases = [
    ("1. I don’t want to live with my family", False),
    ("2. I don’t want to live more with my family", False),
    ("3. I don’t want to live anymore", True),
    ("4. I don’t want to live with my family, but I want to die tonight", True),
    ("5. I have zero intention of hurting myself", False),
    ("6. I don’t want to die, but I am going to kill myself tonight", True),
    ("7. I feel hopeless and wish I would not wake up", True),
    ("8. Ngl I have had enough and want to die tonight", True),
    ("9. Not gonna lie im tryna catch the bus fr", True),
    ("10. Sorry I couldn’t be stronger for you", True),
]

print("=== EVALUATING 10 CRITICAL SAFETY CASES ===")
for text, expected in cases:
    res = evaluate_deterministic_crisis(text)
    is_crisis = res["is_crisis"]
    cat = res.get("matched_category")
    status = "PASS" if (is_crisis == expected or (expected and is_crisis)) else "FAIL"
    print(f"[{status}] {text}")
    print(f"       Result: is_crisis={is_crisis}, category={cat}, bypass={res.get('is_bypassed')}, reason={res.get('bypass_reason')}")
