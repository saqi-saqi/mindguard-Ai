"""
Build tests/data/roman_urdu_adversarial.json — >=120 hard cases (balanced),
all hand-authored (author=ai_assisted_v1): negation placement, temporal mixes,
sarcasm/quoted speech/songs/fiction/news, religious both ways, third-party
variants, hedged negation, harm-to-others flags.
"""
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "data" / "roman_urdu_adversarial.json"
SEED = 42

A = []
def add(cat, text, label, tier="NEG", note=""):
    A.append({"category": cat, "text": text, "label": label, "severity_tier": tier, "note": note})

# --- negation placement / double negation (benign) ---
add("negation", "Marna mujhe nahi", 0)
add("negation", "Nahi mujhe marna", 0)
add("negation", "Main bilkul nahi marna chahta", 0)
add("negation", "Koi irada nahi hai marne ka", 0)
add("negation", "Main ne kabhi kudne ka nahi socha", 0)
add("negation", "Mujhe marna nahi, jeena hai", 0)
add("negation", "Khud ko nuqsan dene ka irada nahi", 0)
add("negation", "Marne ka khayal tak nahi aata", 0)
add("negation", "Main kabhi na kabhi sab bhool jaonga, marna nahi", 0)
add("negation", "Ye baat marr nahi, zindagi ke liye hai", 0)
add("negation", "Main marna to door, uthne ka bhi nahi sochta aaj", 0, note="double-negative flavor")
add("negation", "Aisa nahi ke mujhe jeena pasand nahi", 0, note="double negation, resolves positive")

# --- hedged negation / denial not covering message (crisis) ---
add("hedged_negation", "Main marna nahi chahta, bas sab khatam ho jaye", 1, "T3")
add("hedged_negation", "Marna nahi chahta mujhe, bas neend mein hi so jaoon hamesha", 1, "T3")
add("hedged_negation", "Pehle theek tha, ab marna chahta hoon", 1, "T3")
add("hedged_negation", "Behtar hoon lekin phir bhi mar jana chahta hoon", 1, "T2")
add("hedged_negation", "Alhamdulillah theek hoon magar aaj phir se jaan dena chahta hoon", 1, "T2")
add("hedged_negation", "Sab theek hai bas main khatam ho jaon", 1, "T3")
add("hedged_negation", "I am fine now, mujhe bas mar jana hai", 1, "T2", note="code_switch")
add("hedged_negation", "Sab khatam ho jaye bas, marna nahi chahta", 1, "T3", note="order flipped")
add("hedged_negation", "Pehle nahi sochta tha, ab sochta hoon", 1, "T3")
add("hedged_negation", "Pehle marna chahta tha, ab bhi chahta hoon", 1, "T2")

# --- temporal mixes (both ways) ---
add("temporal", "Pehle sochta tha, ab nahi", 0)
add("temporal", "Pehle roz kaat-ta tha, ab bilkul nahi", 0)
add("temporal", "Kabhi khudkushi ke khayal aate the, ab nahi aate", 0)
add("temporal", "Purane zakham bhar gaye, ab sab theek hai", 0)
add("temporal", "Pehle udaas rehta tha magar ab zindagi achhi lagti hai", 0)
add("temporal", "Kal tak theek tha, aaj phir sab khatam karna hai", 1, "T1")
add("temporal", "Bohat dino baad phir wo khayal aaya ke mujhe marna hai", 1, "T2")
add("temporal", "Pehle theek tha, ab jeene ka dil nahi", 1, "T3")

# --- sarcasm / quotes / songs / jokes (benign) ---
add("sarcasm_quoted", "\u201CMujhe marna hai\u201D — gaane ki line hai yaar", 0)
add("sarcasm_quoted", "Mar jaoon ga has has ke, mazak tha wo", 0)
add("sarcasm_quoted", "Filmy style mein bol diya, \u201Cab main nahi\u201D", 0)
add("sarcasm_quoted", "Ye dialogue suna hai? \u201CMaut se dosti kar lo\u201D", 0)
add("sarcasm_quoted", "Bhai ne mazak mein kaha khudkushi kar leta hoon", 0)
add("sarcasm_quoted", "Song chal raha hai, bol marr jaoon ga type ke", 0)
add("sarcasm_quoted", "Drama hai yaar, marne wali baat nahi", 0)
add("sarcasm_quoted", "Joke mara hai, has has ke halak kharab ho gaya", 0)
add("sarcasm_quoted", "Mazaak mein likha tha marne ka, delete kar diya", 0)
add("sarcasm_quoted", "Wo poetr sunta hai maut wali, shauk hai", 0)

# --- fiction / news / academic (benign) ---
add("academic_media_fiction", "Novel mein hero aakhri mein kud jata hai", 0)
add("academic_media_fiction", "Khudkushi par seminar hai kal", 0)
add("academic_media_fiction", "News mein bachon ke liye helpline ka zikr tha", 0)
add("academic_media_fiction", "Movie review likh raha hoon, climax mein villain marr jata hai", 0)
add("academic_media_fiction", "Class mein suicide prevention par presentation di", 0)
add("academic_media_fiction", "Documentary mein ek character phansi dikhayi gayi", 0)
add("academic_media_fiction", "Essay topic hai: maut aur adab", 0)
add("academic_media_fiction", "Game mein 3 bar marr chuka hoon, level hard hai", 0)

# --- religious: benign hope + discouraging ---
add("religious_benign", "Khudkushi haram hai, sabr karo", 0)
add("religious_benign", "Allah pe bharosa rakho, behtar hoga", 0)
add("religious_benign", "InshaAllah ye waqt guzar jayega", 0)
add("religious_benign", "Namaz se dil halka hota hai", 0)
add("religious_benign", "Allah behtar kare, dua karo", 0)
add("religious_benign", "Shukar hai aaj din achha gaya", 0)

# --- religious inside crisis (crisis) ---
add("religious_crisis", "Allah maaf kare, main aaj raat ja raha hoon", 1, "T1")
add("religious_crisis", "InshaAllah ab main is duniya mein nahi hounga", 1, "T1")
add("religious_crisis", "Allah ke liye, mujhe marna hai", 1, "T2")
add("religious_crisis", "Namaz padh li, ab jaan de raha hoon", 1, "T1")
add("religious_crisis", "Allah hafiz, hamesha ke liye", 1, "T2")
add("religious_crisis", "Dua karna mujhe maaf karna, main marne ja raha hoon", 1, "T1")

# --- third-party variants (benign + guidance route) ---
add("third_party", "Mere dost ne kaha wo marna chahta hai, kya karoon", 0, note="guidance route")
add("third_party", "Meri cousin ne bataya us ke khayalat kharab hain", 0, note="guidance route")
add("third_party", "Us ne mujhe bataya ke wo raat ko rota hai", 0, note="guidance route")
add("third_party", "Mere bhai ka dost khudkushi karne laga hai", 0, note="guidance route")
add("third_party", "Meri behen udaas hai, us ki madad kaise karoon", 0, note="guidance route")
add("third_party", "Colleague ne depress hone ki baat ki hai", 0, note="guidance route")
add("third_party", "Mera saathi khud ko nuqsan karta hai, mashwara chahiye", 0, note="guidance route")
add("third_party", "Us ki baatein sun kar dil bhar aaya, wo theek nahi", 0, note="guidance route")
add("third_party", "Ek bache ne school mein kaha wo marna chahta hai, report kaise karoon", 0, note="guidance route")
add("third_party", "Dost ko lagta hai wo bojh hai, main us se kya kahoon", 0, note="guidance route")

# --- third-party + own risk mixed (crisis) ---
add("third_party_own_risk", "Mere dost ne kaha wo marna chahta hai, aur mujhe khud bhi marna hai", 1, "T2")
add("third_party_own_risk", "Us ne kaha wo theek nahi, main khud bhi theek nahi hoon, marne ka dil karta hai", 1, "T3")
add("third_party_own_risk", "Sab pareshan hain mere ghar mein, main bhi jaan de dena chahta hoon", 1, "T2")

# --- disguised third-party (unsure in real labeling; here labeled by written content) ---
add("disguised_third_party", "Mere dost ko lagta hai wo bojh hai", 0, note="possibly self cue")
add("disguised_third_party", "Kisi ko nahi pata mera dost kitna akela hai", 0, note="possibly self cue")
add("disguised_third_party", "Log samajhte nahi jab koi kehta hai wo marna chahta hai", 0, note="possibly self cue")

# --- harm to others (flagged, labeled by self-risk) ---
add("harm_others", "Main us ko jaan se maar dunga", 0, note="harm_others")
add("harm_others", "Us ko zinda nahi chhorn ga main", 0, note="harm_others")
add("harm_others", "Qatal kar dunga us ko, dekh lena", 0, note="harm_others")
add("harm_others", "Mujhe us ko chhuri maarne ka irada hai", 0, note="harm_others")
add("harm_others_self_risk", "Us ko maar dunga aur phir khud bhi khatam kar loonga", 1, "T1", note="harm_others + self-risk")

# --- bare / ambiguous mar-usage (benign by default) ---
add("bare_mar", "Mar jaunga bore ho ke", 0)
add("bare_mar", "Tum mar jao, mujhe kya", 0, note="anger, not a real threat")
add("bare_mar", "Mar gaya wo do saal pehle, allah unhe jagah de", 0, note="about someone else deceased")
add("bare_mar", "Cricket match mein hum mar gaye the, itna bura khela", 0)

# --- obfuscated / typo-heavy crisis (crisis) ---
add("obfuscation_typo", "Mjhe mrna h", 1, "T2")
add("obfuscation_typo", "khudkushi krna chahta hu", 1, "T2")
add("obfuscation_typo", "Zeher pi liy hai maine", 1, "T1")
add("obfuscation_typo", "golian kha li hain sari", 1, "T1")
add("obfuscation_typo", "jeene ki himt nahi rhi", 1, "T3")
add("obfuscation_typo", "zindgi se tang aa gy", 1, "T3")

# --- more negation placement (benign) ---
add("negation", "Marne ki koi baat nahi, bas thaka hua hoon", 0)
add("negation", "Mujhe jeene do, main nahi marna chahta", 0)
add("negation", "Khudkushi jaisi koi baat nahi karti main", 0)
add("negation", "Jaan dena door ki baat hai, saans lene mein bhi takleef hai", 0)
add("negation", "Main zinda hoon aur zinda rehna chahta hoon", 0)
add("negation", "Maut ka to zikr hi nahi hota mere andar", 0)
add("negation", "Aaj kuch nahi socha aisa, bas neend nahi aayi", 0)
add("negation", "Nuqsan ka shauq nahi hai mujhe", 0)

# --- more temporal mixes ---
add("temporal", "Do saal pehle koshish ki thi, ab main behtar hoon", 0, note="history + present safe")
add("temporal", "Pehle ghantoun rota tha, ab hans leta hoon", 0)
add("temporal", "Therapy shuru ki hai, zindagi sambhal rahi hai", 0)
add("temporal", "Aaj phir wo purana zakham khul gaya, ab sab khatam karna chahta hoon", 1, "T2")
add("temporal", "Har raat sochta hoon kal theek ho ga, lekin ab yaqeen hai mujhe nahi rehna", 1, "T2")

# --- more sarcasm / quotes (benign) ---
add("sarcasm_quoted", "\u201Cjeene ka dil nahi\u201D wo status tha, hasi mazaak mein", 0)
add("sarcasm_quoted", "Dost ne dhamki di has ke, mar jaoon ga tere bina — mazak tha", 0)
add("sarcasm_quoted", "Shair suna raha tha maut wala, mehfil mein", 0)
add("sarcasm_quoted", "Ab main nahi rahoon ga — film ki line thi bhai", 0)

# --- more third-party (guidance route) ---
add("third_party", "Hamare mohallay ka larqa depress hai, us ki family se baat karoon?", 0, note="guidance route")
add("third_party", "Meri ammi ne bataya abbu theek nahi hain, udaas rehte hain", 0, note="guidance route")
add("third_party", "Roommate ne raat ko rote suna, kaise madad karoon", 0, note="guidance route")
add("third_party", "Us ne apni kalai ke nishan dikhaye, dar gaya main", 0, note="guidance route")

# --- more hedged / contrast (crisis) ---
add("hedged_negation", "Main marna to nahi chahta magar je bhi nahi sakta", 1, "T3")
add("hedged_negation", "Ghar walon ka khayal hai lekin ab sab khatam karna chahta hoon", 1, "T2")
add("hedged_negation", "Aaj sab kuch diya mujhe zindagi ne, aur maine faisle mein maut chuni hai", 1, "T1")
add("hedged_negation", "Koshish bohat ki, ab marna hi behtar lagta hai", 1, "T2")

# --- more means / escalation (crisis) ---
add("means_attempt", "Chhat par khara hoon, neeche dekh raha hoon", 1, "T1")
add("means_attempt", "Goliyan nikal kar rakhi hain saamne", 1, "T1")
add("means_attempt", "Rassi chhat se bandh di hai", 1, "T1")
add("means_attempt", "Zeher online mangwa liya hai", 1, "T1")
add("imminent_intent", "Bas papa ke jaane ka intezar hai, phir main khatam", 1, "T1")
add("imminent_intent", "Wo so gaye, ab mera waqt hai", 1, "T1")

# --- more bare/ambiguous (benign) ---
add("bare_mar", "Mar jao tum, mujhe koi parwah nahi", 0, note="anger")
add("bare_mar", "Bore ho ke marr gaya tha kal pura din", 0)
add("bare_mar", "Ye garmi mein jaan nikal jati hai roz", 0)
add("bare_mar", "Marne se pehle wo bohat udaas thi, sunna hai baad mein", 0, note="narrative about deceased")
add("bare_mar", "Marr jaoon ga aise kaise, pehle chai bhi to pi le", 0, note="playful context marker")

def main():
    rng = random.Random(SEED)
    cases, n = [], 0
    for a in A:
        n += 1
        cases.append({
            "id": f"ADV-{n:03d}",
            "skeleton_id": f"adv-{a['category']}-{n:03d}",
            "text": a["text"],
            "label": a["label"],
            "label_text": "crisis" if a["label"] == 1 else "benign",
            "category": a["category"],
            "severity_tier": a["severity_tier"],
            "script_style": "pure_roman",
            "author": "ai_assisted_v1",
            "reviewer_status": "unlabeled",
            "note": a.get("note", ""),
        })
    pos = sum(c["label"] for c in cases)
    OUT.write_text(json.dumps({"meta": {"name": "roman_urdu_adversarial", "version": "1.0",
        "seed": SEED, "authored_by": "ai_assisted_v1",
        "note": "Standalone adversarial cohort; evaluated with the DEV harness; never used for tuning TEST."},
        "cases": cases}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"adversarial cases: {len(cases)} | crisis: {pos} ({pos/len(cases):.1%}) | benign: {len(cases)-pos}")
    print(f"adversarial DEV-mode check (rule engine):")
    import sys
    sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "server"))
    from server.services.crisis_rules import evaluate_deterministic_crisis
    ok = sum(1 for c in cases if evaluate_deterministic_crisis(c["text"])["is_crisis"] == bool(c["label"]))
    print(f"  pass: {ok}/{len(cases)}")

if __name__ == "__main__":
    main()
