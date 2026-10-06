"""
Roman Urdu text normalizer (Stage 2).

Used ONLY when the router says the message is Roman Urdu (ROUTE_URDU or the
Urdu half of ROUTE_BOTH). English text passes through byte-identical —
guaranteed by the router gate plus a property test (500 samples).

Fold policy (justified pair-by-pair; FOLD_JUSTIFICATIONS + the enforcing test):

FOLDED (spelling variants of the same word — meaning preserved):
  nahin / nai / nhe / naheen      -> nahi   (all = "no/not")
  jaonga / jaon ga / jaao ga / jaun ga -> jaunga (1st-person "will go/die")
  chahtaa / chahtey               -> chahta · chahtee -> chahti ("want")
  krta / krna / krti              -> karta / karna / karti (texting shorthand)
  mjhe                            -> mujhe
  khud kushi / khud-kushi         -> khudkushi (spacing variants)
  runs of 3+ identical characters -> 1, ONLY when the collapsed token is a
  known Urdu word ("marrrr" -> "mar"); never on English ("sooo" stays).

NOT FOLDED (meaning-changing, forbidden — enforced by test):
  mein (in/inside) vs main (I) · mar (die) vs marr (beat) · na vs nahi
"""
import re
from typing import List, Tuple

from .roman_urdu_router import _URDU_TOKENS

_WORD = re.compile(r"[A-Za-z]+")
_REPEAT3 = re.compile(r"(.)\1{2,}", re.IGNORECASE)
_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F000-\U0001F02F"
    "\U00002600-\U000026FF\U0001F900-\U0001F9FF\uFE0F\u2764]",
    flags=re.UNICODE,
)

FOLD_JUSTIFICATIONS: List[Tuple[str, str, str]] = [
    ("nahin|nai|nhe|naheen", "nahi", "all spellings of the single negator 'no/not'"),
    ("jaonga", "jaunga", "spelling variant of 1st-person 'will go/die'"),
    ("chahtaa|chahtey", "chahta", "variant spellings of masculine 'want'"),
    ("chahtee", "chahti", "variant spelling of feminine 'want'"),
    ("krta", "karta", "texting shorthand of 'do (m.)'"),
    ("krna", "karna", "texting shorthand of 'to do'"),
    ("krti", "karti", "texting shorthand of 'do (f.)'"),
    ("mjhe", "mujhe", "texting shorthand of 'me/I'"),
    ("mrna|mrrna", "marna", "typo'd 'marna' (texting) — same word"),
    ("himt", "himmat", "typo'd 'himmat' (courage) — same word"),
    ("zindgi", "zindagi", "typo'd 'zindagi' (life) — same word"),
    ("rhi|rhy", "rahi", "texting shorthand of 'rahi'"),
    ("rha|rhay", "raha", "texting shorthand of 'raha'"),
    ("liy|liah", "liya", "typo'd 'liya' (took) — same word"),
    ("sari", "saari", "variant spelling of 'all (f.)'"),
    ("gy", "gaya", "texting shorthand of 'gaya' (went)"),
    ("gi", "gayi", "texting shorthand of 'gayi' (went, f.)"),
    ("hu", "hoon", "texting shorthand of 'hoon' (am)"),
    ("h", "hai", "single-letter texting shorthand of 'hai' (is) — Urdu-texting idiom, gated on Urdu context"),
    ("jaoon", "jaunga", "double-o spelling of 'will (I) go/die' (bare form; 'jaoon ga' is phrase-folded first)"),
    ("maiin", "main", "typo'd 'main' (I) — doubled vowel"),
    ("bethar", "behtar", "typo'd 'behtar' (better) — metathesis"),
    ("kuhc", "kuch", "typo'd 'kuch' (something) — transposition"),
    ("botle", "bottle", "typo'd 'bottle'"),
    ("kuhd|khuud", "khud", "typo'd 'khud' (self) — letter moved/doubled"),
    ("chhata|chhatta", "chahta", "h-transposition typo of 'chahta' (want)"),
    ("hoo+n", "hoon", "typing emphasis on 'hoon' (am) — repeated letters collapsed"),
    ("akahri", "aakhri", "typo'd 'aakhri' (last)"),
    ("meere", "mere", "typo'd 'mere' (my)"),
    ("liiye", "liye", "typo'd 'liye' (took)"),
    ("diay", "diye", "variant spelling of 'diye' (gave)"),
    ("jaa", "ja", "variant spelling of 'ja' (go)"),
]

FOLD_PHRASES: List[Tuple[str, str, str]] = [
    ("khud kushi", "khudkushi", "same word, spacing variant"),
    ("khud-kushi", "khudkushi", "same word, hyphen variant"),
    ("jaon ga", "jaunga", "nasalized spelling of 'will go/die'"),
    ("jaao ga", "jaunga", "spelling variant of 'will go/die'"),
    ("jaun ga", "jaunga", "nasalized spelling of 'will go/die'"),
]

FOLD_PHRASES += [
    ("jaoon ga", "jaunga", "double-o spelling of 'will go/die'"),
]

FORBIDDEN_FOLDS: List[Tuple[str, str, str]] = [
    ("mein", "main", "'in' vs 'I' — different words"),
    ("mar", "marr", "'die' vs 'beat' — different verbs"),
    ("na", "nahi", "both kept: negation strength differs"),
]

_URDU_CONTEXT_ANCHORS = frozenset([
    "mujhe", "mjhe", "main", "mein", "mera", "meri", "nahi", "nahin", "nai",
    "nhe", "hai", "hain", "hoon", "hu", "karna", "krna", "chahta", "chahti",
    "marna", "mrna", "marr", "mar", "zindagi", "zindgi", "khud", "khudkushi",
    "jaan", "dil", "allah", "inshallah", "alvida", "maaf", "yaar", "tang", "zeher", "bottle", "khali", "bekaar",
    "himmat", "himt", "umeed", "mushkil", "jeena", "maut", "jaunga", "jaonga",
    "chahiye", "rehna", "alhamdulillah", "rha", "rhi", "gy", "gi",
])


def _has_urdu_context(text: str) -> bool:
    for tok in _WORD.findall(text.lower()):
        if tok in _URDU_CONTEXT_ANCHORS:
            return True
        # repeated-letter typing ("marrrr") still counts via its collapsed form
        collapsed = _REPEAT3.sub(r"\1", tok)
        if collapsed != tok and collapsed in _URDU_CONTEXT_ANCHORS:
            return True
    return False


def _edit1_candidates(token: str, lexicon: frozenset):
    """Lexicon words within edit distance 1 of token (insert/delete/substitute)."""
    out = set()
    for w in lexicon:
        if abs(len(w) - len(token)) > 1:
            continue
        if len(w) == len(token):
            diff = sum(1 for a, b in zip(w, token) if a != b)
            if diff == 1:
                out.add(w)
        elif len(w) == len(token) + 1:
            for i in range(len(w)):
                if w[:i] + w[i + 1:] == token:
                    out.add(w)
                    break
        elif len(token) == len(w) + 1:
            for i in range(len(token)):
                if token[:i] + token[i + 1:] == w:
                    out.add(w)
                    break
    return out


# Fuzzy correction targets: crisis-vocabulary anchors only (precision guard —
# never corrects everyday words). Justification: plan §3 fuzz remedy, anchors
# restricted to >= 5 chars AND single unambiguous candidate.
FUZZ_TARGETS = frozenset([
    "marna", "marrne", "marne", "khudkushi", "zeher", "goliyan", "phansi",
    "bandh", "kalai", "ghayab", "hamesha", "behtar", "himmat", "zindagi",
    "sukoon", "maut", "aakhri", "intezar", "alvida", "bojh", "pareshan",
    "chhat", "blade", "rassi", "jaunga", "khayal", "duniya", "irada",
    "ghadi", "jeena", "himmat", "nashiyan", "kerosene", "mangwa",
])


def fuzz_correct(text: str) -> str:
    """Edit-distance-1 correction toward crisis-vocabulary anchors only.
    Applied ONLY on the Urdu path (router-gated). A token is corrected only
    when exactly ONE target word is within distance 1 (ambiguous -> left)."""
    def fix(m: re.Match) -> str:
        w = m.group(0)
        lw = w.lower()
        if len(lw) < 5 or lw in _URDU_TOKENS or lw in FUZZ_TARGETS or lw in _COMMON_NONURDU:
            return w
        cands = _edit1_candidates(lw, FUZZ_TARGETS) - _COMMON_NONURDU
        if len(cands) == 1:
            return cands.pop()
        return w
    return re.sub(r"[A-Za-z]+", fix, text)


_COMMON_NONURDU = frozenset([
    "about", "after", "again", "because", "before", "being", "better", "cannot",
    "come", "coming", "doing", "done", "every", "feel", "feeling", "first",
    "found", "going", "gone", "great", "have", "here", "myself", "never",
    "other", "people", "really", "right", "should", "since", "still", "thank",
    "their", "there", "these", "thing", "think", "those", "through", "today",
    "together", "under", "water", "where", "which", "while", "world", "would",
    "wrote", "years", "your", "movie", "novel", "class", "story", "sleep",
])


def normalize_roman_urdu(text: str) -> str:
    """Normalize Roman Urdu text for rule matching. English input is returned
    UNCHANGED (router gates this; property-tested)."""
    if not text:
        return text or ""
    if not _has_urdu_context(text):
        return text

    out = _ZERO_WIDTH.sub("", text)
    out = _EMOJI.sub(" ", out)

    for pat, rep, _why in FOLD_PHRASES:
        out = re.sub(pat, rep, out, flags=re.IGNORECASE)

    def fix_word(m: re.Match) -> str:
        w = m.group(0)
        lw = w.lower()
        collapsed = _REPEAT3.sub(r"\1", lw)
        if collapsed != lw and collapsed in _URDU_TOKENS:
            return collapsed
        for pat, rep, _why in FOLD_JUSTIFICATIONS:
            if re.fullmatch(pat, lw):
                return rep
        return w

    out = re.sub(r"[A-Za-z]+", fix_word, out)
    out = fuzz_correct(out)
    out = re.sub(r"\s+", " ", out).strip()
    return out
