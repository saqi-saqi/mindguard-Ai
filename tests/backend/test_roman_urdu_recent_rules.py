"""Regression checks for the recently added Roman Urdu crisis patterns.

These are targeted examples, not a replacement for an independent held-out
benchmark. The benign railway examples guard against matching a means/location
phrase without evidence of self-harm intent.
"""

import pytest

from server.services.crisis_rules import evaluate_crisis_pipeline
from server.services.roman_urdu_router import ROUTE_BOTH, ROUTE_URDU, route


@pytest.mark.parametrize(
    "message",
    [
        "Railway track pe meri body milegi",
        "Rassi gale mein daal li hai",
        "Apna gala kaat loonga",
        "Zehreeley chemical se apna khatma karunga",
        "Aj meri aakhri post hai social media pe",
    ],
)
def test_recent_roman_urdu_crisis_examples_are_detected(message):
    language_route, _ = route(message)
    result = evaluate_crisis_pipeline(message, allow_ml_fallback=False)

    assert language_route in (ROUTE_URDU, ROUTE_BOTH)
    assert result["is_crisis"], f"Expected crisis detection for: {message!r}"
    assert result["risk_level"] in ("high", "imminent")
    assert result["source"] == "deterministic_rules"


@pytest.mark.parametrize(
    "message",
    [
        "Railway track par train chalti hai",
        "Main railway track par train ka wait kar raha hoon",
        "Mujhe khud ko nuqsan dene ka koi plan nahi hai",
        "Traffic mujhe maar dalega, bohat jam laga hua hai",
        "Someone online ne khud ko nuqsan dene ki baat ki, main report karun?",
        "Garmi mujhe maar dalegi, bohot dhoop hai",
        "Yeh exam mujhe maar dalega",
        "Load shedding mujhe maar dalegi",
        "Main apne aap ko hurt nahi karunga, main bilkul safe hoon",
        "Mere paas khud ko nuqsan pohanchane ka koi irada nahi hai",
        "Rail ki patri ke paas station ka board laga hai",
    ],
)
def test_railway_track_alone_does_not_trigger_crisis(message):
    result = evaluate_crisis_pipeline(message, allow_ml_fallback=False)

    assert not result["is_crisis"], (
        f"A benign or negated Roman Urdu mention was escalated: {message!r} -> {result}"
    )


@pytest.mark.parametrize(
    "message",
    [
        # Verified previously missed crisis skeletons
        "Zindagi khatam karna chahta hoon",
        "Ab mujhse zinda nahi raha jata",
        "Mujhe apne aap ko khatam karna hai",
        "Main chhat se koodne wala hoon",
        "Maine apni zindagi khatam karne ka faisla kar liya hai",
        "I want to khatam my life, ab aur nahi hota",
        "Main blade se apni kalai kaatne ja raha hoon",
        "Maine apne aap ko zakhmi kar liya hai",
        "Main khud ko hurt karne wala hoon",
        "Mere baad sab ko keh dena ke main maafi chahta tha",
        "Yeh mera aakhri paighaam hai, main ja raha hoon",
        "Ab tum sab mujhe dobara nahi dekhoge",
        # Independently authored examples testing the same grammatical families
        "Apni zindagi khatam karne ka soch raha hoon",
        "Mujhse ab aur zinda nahi raha jata",
        "Main building se koodne wala hoon",
        "Blade se kalai kaatne ja raha hoon",
        "Main khud ko chot pohanchane ka soch raha hoon",
        "Yeh mera aakhri message hai dosto, mujhe maaf kar dena",
        "Main sab se alvida keh raha hoon kyun ke ab jeena nahi hai",
    ],
)
def test_generalized_roman_urdu_crisis_patterns_detected(message):
    language_route, _ = route(message)
    result = evaluate_crisis_pipeline(message, allow_ml_fallback=False)

    assert language_route in (ROUTE_URDU, ROUTE_BOTH)
    assert result["is_crisis"], f"Expected crisis detection for: {message!r}"
    assert result["risk_level"] in ("high", "imminent")
    assert result["source"] == "deterministic_rules"


