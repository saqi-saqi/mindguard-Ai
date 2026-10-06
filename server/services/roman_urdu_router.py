"""
Roman Urdu language router.

Decides whether a message should go through the Roman-Urdu detection path,
the English path, both (borderline -> more severe result wins), or the
Arabic-script fallback (Urdu/Nastaliq script is out of scope for detection
but must never be treated as "nothing to see").

Route contract (tested in tests/backend/test_roman_urdu_engine.py):
  - Pure English messages are never routed to the Urdu-only path.
  - Code-switched messages containing Urdu anchors are routed to the Urdu path.
  - Borderline messages route to BOTH paths (caller takes the more severe).
  - Arabic-script input returns ROUTE_ARABIC_SCRIPT (caller shows a gentle
    generic check-in with resources; never "non-crisis, nothing to see").
"""
import re
from typing import Tuple

# High-signal Roman Urdu tokens (function words + common content words).
# Deliberately conservative: "yaar" alone must NOT force the Urdu path.
_URDU_TOKENS = frozenset("""
mujhe mjhe mujhay main mein mera meri mere meray hum humara apna apni apne
tum tumhara tumhari tmhara ye yeh wo woh jo
ka ki ke ko se par hai hain hoon ho thay thi the
kya kyun kaise kab kahan koi kuch sab har
nahi nahin nai nhe bilkul kabhi
ab abhi aaj kal raat din subah shaam waqt
tha thi the hua hui howa raha rahi rahe wala wali
karna karne kar karke kar liya kar li khatam khatam-karna
zindagi jaan marna marr mar mare marrna maut mout
jeena jeene jee jee-na jina jeechahta
dil dil- dukh dard sukoon himmat umeed umeedain mushkil aasan
pareshan udaas udaasi tang thaka thak haar har-gaya bekaar
khush khushy khushi roona rona ro raha rote ansu aansu
khud khudkushi khud-kushi khudkushy
phansi faansi zeher zehar goli goliyan golian nasha nashe
chhat chhatt kudna kud blade churi chhuri kalai kalaai zakham zakhmi
dawa dawai dawaian neend ki-goliyan
alvida allah-hafiz allah allahke allahse allahka inshallah insha-allah
inshaallah alhamdulillah alhamdo mashallah mashaallah dua dua-karo namaz
maaf bohat bahut bohatt sachi sachi-much yaar pata
acha achha achay theek thik behtar bhalai bura buri
jata jati jate laga lag raha lagta lagti chahiye chahye
dekho dekhta dekhti sun suno sunn batao bata
ghar walon walid ghar-wale dost doston bhai behen bahan ammi abbu
""".split())

_ARABIC_SCRIPT = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
_WORD = re.compile(r"[A-Za-z\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]+")


def _tokenize(text: str):
    return _WORD.findall(text or "")


def urdu_density(text: str) -> float:
    """Share of alphabetic tokens that are Roman Urdu anchors (0..1)."""
    toks = [t.lower() for t in _tokenize(text)]
    if not toks:
        return 0.0
    hits = sum(1 for t in toks if t in _URDU_TOKENS)
    return hits / len(toks)


def has_arabic_script(text: str) -> bool:
    return bool(_ARABIC_SCRIPT.search(text or ""))


ROUTE_ENGLISH = "english"
ROUTE_URDU = "roman_urdu"
ROUTE_BOTH = "both"
ROUTE_ARABIC_SCRIPT = "arabic_script"


def route(text: str) -> Tuple[str, float]:
    """Returns (route, urdu_density). Never raises on odd input."""
    if has_arabic_script(text):
        return ROUTE_ARABIC_SCRIPT, 0.0
    toks = [t.lower() for t in _tokenize(text)]
    hits = sum(1 for t in toks if t in _URDU_TOKENS)
    d = hits / len(toks) if toks else 0.0
    if hits >= 2 or (hits == 1 and d >= 0.4):
        return ROUTE_URDU, d
    if hits == 1:
        return ROUTE_BOTH, d
    return ROUTE_ENGLISH, d
