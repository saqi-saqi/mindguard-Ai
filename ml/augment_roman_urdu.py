"""
Roman Urdu training-data synthesizer (Stage 4 — NOT run automatically).

Generates ~20-25k balanced Roman Urdu samples from template grammars:
  crisis (all tiers x means/intent/goodbye/self-harm) and benign
  (distress, physical, hyperbole, negation, recovery), each with 3 noise
  levels (clean / spelling variants / typos) + code-switch mixing.

Guards (plan §7):
  - template-diversity report: FAIL if any single template > 2% share
  - exact-text dedupe AFTER generation (counts reported)
  - DISJOINT from benchmark skeletons (validated by tests/backend test +
    scripts/check_ml_disjoint.py): template phrasings differ from corpus.
Output: ml/data/roman_urdu_augmented.csv (text,label)
Usage:  python ml/augment_roman_urdu.py
"""
import csv
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "ml" / "data" / "roman_urdu_augmented.csv"
SEED = 42
TARGET_PER_SIDE = 11000

# Crisis templates: {p} pronoun-set, {v} variant — each expands deterministically.
CRISIS_TEMPLATES = [
    "mujhe marna hai", "mujhe {t} marna hai", "main marna chahta hoon", "main marna chahti hoon",
    "ab mujhe jeena nahi hai", "mujhe apni jaan deni hai", "khudkushi karna chahta hoon",
    "khudkushi ka soch raha hoon", "zindagi khatam karna chahta hoon", "ab sab khatam karna hai",
    "mujhe bas mar jana hai", "main se ab kuch nahi hota", "ab jeene ka dil nahi karta",
    "sab behtar hoga mere bina", "main sab ka bojh hoon", "sab ko alvida keh raha hoon",
    "mujhe maaf kar dena sab ko, main ja raha hoon", "ab main hamesha ke liye ja raha hoon",
    "aaj raat marna chahta hoon", "aaj hi sab khatam kar loonga", "marrne ka waqt aa gaya hai",
    "goliyan kha li hain maine", "zeher pi liya hai", "zeher kharid liya aaj hi",
    "phansi laga li hai", "chhat se kudne wala hoon", "neend ki goliyan kha li bohat saari",
    "rassi chhat se bandh di hai", "gas chula laga hai ab", "blade se kalai kaat li hai",
    "main apni kalai kaat raha hoon", "main khud ko nuqsan pahunchata hoon",
    "dard mein hi sukoon milta hai", "aaj phir khud ko kaat baitha hoon",
    "jeene ki himmat nahi rahi", "zindagi se tang aa gaya hoon", "koi umeed nahi rahi ab",
    "andhera hi andhera hai", "sukoon nahi milta kahin", "sab bekaar lagta hai ab",
    "mar jaoon to sab samajh jayenge", "kash neend na tootey kabhi",
    "duniya se jaana chahta hoon", "maut hi rahat hai mere liye", "ab maut chuni hai maine",
    "bas thoda waqt aur phir main khatam", "ghadi dekh raha hoon bas waqt aa gaya",
    "papa ke jaane ke baad main bhi khatam", " sab ko salam main ja raha hoon",
]
BENIGN_TEMPLATES = [
    "aaj ka din theek tha", "thoda thaka hoon kaam se", "bhook lagi hai yaar",
    "neend nahi aayi raat bhar", "bukhar hai kal se", "sir dard kar raha hai",
    "exam ki tayari chal rahi hai", "movie achhi lagi kal", "dost ke saath ghoomne gaya tha",
    "garmi bohat hai aaj kal", "chai pi lo dukh khatam", "match dekha raat ko, maza aaya",
    "naya saal pe nayi ummeedein", "kaam bohat tha par ho gaya", "sab theek chal raha hai",
    "aaj mood achha hai", "family ke saath dinner kiya", "cricket dekhne ka plan hai",
    "bore ho raha hoon aaj", "thodi si khansi hai bas", "workout ke baad jism dukh raha hai",
    "assignment khatam kar loon phir dekhte hain", "dost mila bohat dino baad",
    "barish ho rahi hai, chai ke liye best", "naya phone liya hai", "salary aa gayi is mahine",
    "ghar walon se baat hui, sab khush", "thaka hoon par khush hoon", "kal chutti hai",
    "net slow hai aaj kal", "naya drama shuru kiya, story achhi hai",
    # distress without death-wish (label 0 — support, not crisis)
    "bohat pareshan hoon kaam ki wajah se", "udaas feel kar raha hoon aaj",
    "dost se larai ho gayi, bura lag raha hai", "results ki tension hai",
    "ghar mein thodi larai ho gayi", "akela feel kar raha hoon aaj",
    "mushkil waqt hai par guzar jayega", "himmat nahi har rahi bas thaka hoon",
    # hyperbole
    "garmi ne maar dala aaj", "bhook se mar jaunga", "has has ke mar jaunga",
    "exam ne maar dala", "bore ho ke mar jaunga", "traffic ne jaan nikal di",
    "itni thakan ke mar jaun", "mar hi jaoon ga itni garmi mein",
    # negation
    "main marna nahi chahta", "khudkushi jaisi baat nahi", "maut nahi chahiye mujhe",
    "kabhi aisa socha nahi", "khud ko nuqsan nahi pahunchaunga", "jeene ka dil karta hai",
    # recovery
    "pehle sochta tha ab nahi", "alhamdulillah ab theek hoon", "purani aadat chhor di",
    "ab zindagi achhi lag rahi hai", "therapy se behtar feel hota hai",
]
CODE_SWITCH_HEADS = ["yaar ", "I swear ", "honestly ", "sachi ", "pata hai ", "for real, "]
CODE_SWITCH_TAILS = [", I am done", ", seriously", ", for real", ", not joking"]
SPELL_MAP = [(r"\bnahi\b", ["nahin", "nai", "nhe"]), (r"\bhai\b", ["he", "h"]),
             (r"\bchahta\b", ["chahtaa"]), (r"\bchahti\b", ["chahtee"]),
             (r"\bmujhe\b", ["mjhe"]), (r"\bhoon\b", ["hu"]), (r"\bkarta\b", ["krta"]),
             (r"\bkarna\b", ["krna"]), (r"\bjaunga\b", ["jaonga"]), (r"\bkhudkushi\b", ["khud kushi"])]
VOWELS = "aeiou"


def typo(text: str, rng: random.Random, level: int) -> str:
    words = text.split(" ")
    n_typos = level  # 1..3
    for _ in range(n_typos):
        idxs = [i for i, w in enumerate(words) if len(w) >= 4]
        if not idxs:
            break
        i = rng.choice(idxs)
        w = list(words[i])
        j = rng.randrange(1, len(w) - 1)
        op = rng.choice(["swap", "drop", "dup"])
        if op == "swap" and j + 1 < len(w):
            w[j], w[j + 1] = w[j + 1], w[j]
        elif op == "drop":
            del w[j]
        else:
            w.insert(j, w[j])
        words[i] = "".join(w)
    return " ".join(words)


def variant(text: str, rng: random.Random) -> str:
    style = rng.random()
    if style < 0.25:  # code-switch
        if rng.random() < 0.5:
            return rng.choice(CODE_SWITCH_HEADS) + text
        return text + rng.choice(CODE_SWITCH_TAILS)
    if style < 0.5:  # spelling variants
        out = text
        for pat, reps in SPELL_MAP:
            if re.search(pat, out) and rng.random() < 0.6:
                out = re.sub(pat, rng.choice(reps), out, count=1)
                break
        return out
    if style < 0.8:  # typos level 1-3
        return typo(text, rng, rng.randint(1, 3))
    return text  # clean


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.lower()).strip()


def _benchmark_norms() -> set:
    """Normalized texts of every benchmark case (DEV + TEST + adversarial):
    ML data must be disjoint from all of them (plan §D)."""
    bans = set()
    for f in ["tests/data/roman_urdu_benchmark.json", "tests/data/roman_urdu_adversarial.json"]:
        p = ROOT / f
        if p.exists():
            for c in json.loads(p.read_text(encoding="utf-8"))["cases"]:
                bans.add(norm(c["text"]))
    return bans


BANNED = _benchmark_norms()


def main():
    rng = random.Random(SEED)
    rows = []
    per_template = Counter()
    # crisis side: each template expanded with variants to fill quota
    per_tpl_crisis = TARGET_PER_SIDE // len(CRISIS_TEMPLATES) + 1
    for tpl in CRISIS_TEMPLATES:
        made = 0
        seen = set()
        attempts = 0
        while made < per_tpl_crisis and attempts < per_tpl_crisis * 30:
            attempts += 1
            t = tpl if made == 0 else variant(tpl, rng)
            if norm(t) in seen:
                continue
            seen.add(norm(t))
            rows.append((t, 1))
            per_template[tpl] += 1
            made += 1
    per_tpl_benign = TARGET_PER_SIDE // len(BENIGN_TEMPLATES) + 1
    for tpl in BENIGN_TEMPLATES:
        made = 0
        seen = set()
        attempts = 0
        while made < per_tpl_benign and attempts < per_tpl_benign * 30:
            attempts += 1
            t = tpl if made == 0 else variant(tpl, rng)
            if norm(t) in seen:
                continue
            seen.add(norm(t))
            rows.append((t, 0))
            per_template[tpl] += 1
            made += 1

    # exact dedupe (reported)
    before = len(rows)
    seen = set()
    deduped = []
    banned_hits = 0
    for t, l in rows:
        k = norm(t)
        if k in BANNED:
            banned_hits += 1
            continue
        if k in seen:
            continue
        seen.add(k)
        deduped.append((t, l))
    rng.shuffle(deduped)
    print(f"benchmark-overlap rows excluded: {banned_hits}")

    max_share = max(per_template.values()) / len(deduped)
    print(f"rows: {before} -> {len(deduped)} after exact dedupe")
    print(f"templates: {len(per_template)} | max template share: {max_share:.2%} "
          f"({'PASS <=2%' if max_share <= 0.02 else 'FAIL >2%'})")
    print(f"crisis: {sum(l for _, l in deduped)} | benign: {sum(1 for _, l in deduped if l == 0)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["text", "label"])
        for t, l in deduped:
            w.writerow([t, l])
    print(f"wrote {OUT}")
    if max_share > 0.02:
        print("TEMPLATE DIVERSITY GATE FAILED — add more templates")
        sys.exit(1)


if __name__ == "__main__":
    main()
