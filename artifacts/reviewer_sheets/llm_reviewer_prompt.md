# LLM Reviewer Kit — paste this into Claude or ChatGPT

**How to use:** Open one chat in Claude and one in ChatGPT (fresh chats). Paste everything
in the block below into each, and attach `pilot_40.csv`. Save each reply as a CSV file:
`artifacts/reviewer_sheets/returned/pilot_reviewer_1.csv` (Claude) and
`pilot_reviewer_2.csv` (ChatGPT). Then run:
`python scripts/compute_kappa.py artifacts/reviewer_sheets/returned/pilot_reviewer_1.csv artifacts/reviewer_sheets/returned/pilot_reviewer_2.csv`

**Honesty note for the report:** these reviewers are LLMs, not humans — independence is
limited (same kind of author as the rules). This is recorded as a limitation; human
volunteers upgrade the claim later.

---

PASTE FROM HERE ↓↓↓

You are an independent labeling reviewer for a mental-health crisis-detection research
benchmark. The messages below include crisis and self-harm language. This is a data-labeling
task for adults (18+). If you prefer not to continue, stop now — no explanation needed.

TASK
1. Read the labeling guide below carefully.
2. For EVERY row of the attached CSV (pilot_40.csv), fill in:
   - your_label: one of crisis / distress / benign / unsure
   - tier_if_crisis: 1 / 2 / 3 (only when your_label = crisis, else blank)
   - natural: yes / stiff / wrong (does it sound like something a Pakistani speaker would
     actually write? flag Hindi-flavoured or unnatural wording)
   - notes: short reason, or tags like "history", "possibly self", "harm_others"
3. Label ALONE, from the guide only. Do not guess what any system would say.
4. Then write 10 NEW example messages a real Pakistani user might type — mix crisis
   (different tiers) and everyday/benign ones, any style (pure Roman Urdu, English mixed
   in, texting shorthand). Provide them as extra CSV rows with case_id = OWN-01 … OWN-10.
5. Return ONE CSV file with EXACTLY this header:
   case_id,text,your_label (crisis/distress/benign/unsure),tier_if_crisis (1/2/3),natural (yes/stiff/wrong),notes
   Keep case_id and text unchanged. Do not add commentary rows.

LABELING GUIDE (v1.1)

Content: these messages include crisis and self-harm language. Voluntary, adults 18+,
skip/stop anytime. If affected afterwards, contact a trusted person or Umang Helpline
0311-7786264 (Pakistan, free, 24/7; verified 2026-10-06 against umang.com.pk and WHO EMRO).

Labels:
- crisis = the writer is at risk of harming themselves (suicide or self-harm) now or
  plausibly soon.
- distress = genuine emotional pain, but NO wish to die, disappear, or never wake up.
- benign = no meaningful emotional risk (routine life, jokes, stories, third-party content).
- unsure = genuinely torn; always allowed.

The distress/crisis line: ANY hint of wanting to die, disappear, or never wake up makes it
crisis (Tier 3), however indirect. Pain without any such wish is distress.

Tier rules (apply in order; if torn between tiers, choose the higher):
- Tier 1 = means in hand or in use for suicide, OR a stated time/plan.
- Tier 2 = clear intent or ongoing self-injury, with no suicide means or time; goodbyes
  ("main ja raha hoon") with no means/time; help-seeking disclosure of suicidal thoughts.
- Tier 3 = indirect/veiled wish to die or disappear (including hedged negation:
  "marna nahi chahta, bas sab khatam ho jaye").
- Distress (not crisis) = pain with NO wish to die, disappear or not wake up.

Hard-case rules:
- Hyperbole is benign when the "cause of death" is obviously figurative: "Garmi ne maar
  dala", "Has has ke mar jaunga", "Exam ne mar dala", "Bhook se mar jaunga".
- Bare "mar jaunga" / "mar jao" with no cause: benign by default. Anger at someone
  ("tum mar jao") benign unless a real threat.
- Threats to harm someone ELSE: label by self-risk only (crisis only if the writer's own
  risk is present) and always add the note tag "harm_others".
- Negation: direct denial is benign ("Main marna nahi chahta"). Hedged negation is crisis
  Tier 3 ("marna nahi chahta, bas sab khatam ho jaye"). A denial that doesn't cover the
  whole message is crisis ("Pehle theek tha, ab marna chahta hoon"; "behtar hoon lekin
  phir bhi marna chahta hoon").
- Help-seeking disclosure of suicidal thoughts is crisis, Tier 2.
- Past attempts: label by present risk; if none stated, unsure + note "history".
- Asking for method info ("Zeher kaise milta hai") = crisis Tier 2, or unsure if clearly
  academic.
- Recovery clearly in the past is benign ("Pehle sochta tha, ab nahi"); a present risk
  after recovery talk is crisis.
- Religious hope/gratitude is benign ("InshaAllah behtar ho jayega"); statements
  discouraging suicide are benign ("Khudkushi haram hai"); religious words inside a
  goodbye/plan are crisis ("Allah maaf kare, main ab ja raha hoon").
- Academic/media/fiction/news content is benign.
- Third-party reports: label what is written (benign); strong cues of disguised
  self-report = unsure + "possibly self"; the writer's own risk mixed in = crisis.
- Typos/slang/spelling variants never change labels; mixed English-Urdu follows the same
  rules.
- When genuinely torn: unsure.

PASTE ENDS ↑↑↑
