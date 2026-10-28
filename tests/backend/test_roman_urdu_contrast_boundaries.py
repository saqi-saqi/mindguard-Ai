"""
Targeted Boundary & Contrast-Pair Tests for Roman Urdu Crisis Detection.

Verifies linguistic and grammatical boundary behaviors across:
1. Nominal negation contrast: pure denial vs denial followed by active threat/means
2. Burden / goodbye phrasing: benign social speech, fictional, quoted, third-party, and genuine acute farewells
3. Inanimate hyperbole vs vehicular suicide vs threat to others
4. Third-party disclosures vs informational queries vs disguised first-person crisis
"""

import pytest
from server.services.crisis_rules import evaluate_crisis_pipeline
from server.services.threat_actor_detector import analyze_threat_actor_target


# ---------------------------------------------------------------------------
# 1. Nominal Negation vs Active Threat Contrast Pairs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected_crisis,expected_risk",
    [
        # Pure denials: must be suppressed/safe check-in, never escalated to crisis
        ("Mujhe khud ko nuqsan dene ka koi plan nahi hai", False, "LOW_CONFIDENCE_RISK"),
        ("Mera khudkushi karne ka koi irada nahi hai", False, "LOW_CONFIDENCE_RISK"),
        ("Main apne aap ko chot nahi pohanchaunga", False, "none"),
        # Contrast pairs: denial in first clause, but followed by current/imminent threat in subsequent clause
        ("Mujhe nuqsan dene ka koi plan nahi tha lekin ab main chhat se koodne wala hoon", True, "imminent"),
        ("Mera khudkushi ka koi plan nahi hai par ab main building se chalang laga raha hoon", True, "imminent"),
        ("Koi plan nahi hai nuqsan ka par ab bas zindagi khatam karni hai", True, "imminent"),
        ("Pehle mera koi plan nahi tha magar ab main zeher pee raha hoon", True, "imminent"),
        ("Mujhe zakhmi karne ka koi irada nahi hai lekin seedha marna chahta hoon", True, "high"),
    ],
)
def test_nominal_negation_contrast_pairs(text, expected_crisis, expected_risk):
    res = evaluate_crisis_pipeline(text, allow_ml_fallback=False)
    assert bool(res.get("is_crisis")) == expected_crisis, (
        f"Failed crisis expectation for {text!r}: got is_crisis={res.get('is_crisis')}, "
        f"risk={res.get('risk_level')}, source={res.get('source')}"
    )
    if expected_crisis:
        assert res.get("risk_level") in ("high", "imminent")


# ---------------------------------------------------------------------------
# 2. Burden / Goodbye Phrasing Across Five Contexts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,context_type,expected_crisis",
    [
        # (a) Benign social messages: must NOT create high-risk alerts
        ("Yeh mera aakhri message hai aaj ka, kal baat karte hain", "benign", False),
        ("Yeh meri aakhri post hai is group par, main leave kar raha hoon", "benign", False),
        ("Meri aakhri baat suno, kal subah time pe pohnchna", "benign", False),
        # (b) Fictional references: must NOT create high-risk alerts
        ("Is novel mein character ka aakhri message tha", "fictional", False),
        # (c) Third-party disclosures: must route to third-party guidance, not first-person alert
        ("Usne mujhe aakhri message bheja tha ke wo khudkushi kar raha hai", "third_party", False),
        # (d) Genuine acute crisis farewells: must trigger crisis
        ("Yeh mera aakhri message hai sab ke liye, mujhe maaf kar dena, main chhat se kood raha hoon", "crisis", True),
        ("Yeh mera aakhri paighaam hai, ab alvida, sab khush rehna", "crisis", True),
        ("Yeh mera aakhri paighaam hai, main ja raha hoon", "crisis", True),
    ],
)
def test_burden_goodbye_contextual_boundaries(text, context_type, expected_crisis):
    res = evaluate_crisis_pipeline(text, allow_ml_fallback=False)
    assert bool(res.get("is_crisis")) == expected_crisis, (
        f"Context {context_type!r} failed for {text!r}: got is_crisis={res.get('is_crisis')}, "
        f"risk={res.get('risk_level')}, source={res.get('source')}"
    )
    if context_type == "third_party":
        assert res.get("is_third_party") is True, f"Expected is_third_party=True for: {text!r}"


# ---------------------------------------------------------------------------
# 3. Inanimate Hyperbole vs Vehicular Suicide vs Threat to Others
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected_crisis,expected_category",
    [
        # Casual inanimate hyperbole: non-crisis
        ("Traffic mujhe maar dalega", False, "hyperbole"),
        ("Garmi mujhe maar dalegi", False, "hyperbole"),
        ("Exam mujhe maar dalega", False, "hyperbole"),
        ("Mehngai mujhe maar dalegi", False, "hyperbole"),
        # Vehicular suicide: acute first-person crisis
        ("Main traffic mein gari deewar se takra kar jaan de dunga", True, "vehicular_suicide"),
        # Threat to others: threat actor detection fires
        ("Main usko jaan se maar dalunga", True, "threat_to_others"),
    ],
)
def test_inanimate_hyperbole_vs_threat_boundaries(text, expected_crisis, expected_category):
    res = evaluate_crisis_pipeline(text, allow_ml_fallback=False)
    ta = analyze_threat_actor_target(text)
    assert bool(res.get("is_crisis")) == expected_crisis, (
        f"Category {expected_category!r} failed for {text!r}: got is_crisis={res.get('is_crisis')}"
    )
    if expected_category == "threat_to_others":
        assert ta.category == "HARM_TO_OTHERS_RISK"
        assert ta.actor == "user"
    elif expected_category == "hyperbole":
        assert ta.is_threat is False


# ---------------------------------------------------------------------------
# 4. Third-Party Disclosures vs Inquiries vs Disguised First-Person Crisis
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected_crisis,expected_third_party",
    [
        # Real third-party disclosure: friend/family
        ("Meri dost keh rahi hai ke wo khudkushi karegi", False, True),
        # Real third-party disclosure: online contact
        ("Someone online ne kaha ke wo suicide kar raha hai", False, True),
        # Informational inquiry / asking how to help: non-crisis, not acute third-party
        ("Agar koi online suicide ki baat kare to kya karna chahiye", False, False),
        # Disguised first-person crisis: must NOT be diverted to third-party guidance
        ("Maine online kisi ko bataya ke main khudkushi karunga", True, False),
    ],
)
def test_third_party_vs_first_person_boundaries(text, expected_crisis, expected_third_party):
    res = evaluate_crisis_pipeline(text, allow_ml_fallback=False)
    assert bool(res.get("is_crisis")) == expected_crisis, (
        f"Failed crisis expectation for {text!r}: got is_crisis={res.get('is_crisis')}"
    )
    assert bool(res.get("is_third_party")) == expected_third_party, (
        f"Failed third_party expectation for {text!r}: got is_third_party={res.get('is_third_party')}"
    )
