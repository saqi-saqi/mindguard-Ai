"""
MindGuard - Psychoeducational Knowledge Base & Response Engine
---------------------------------------------------------------
Provides structured, evidence-based coping responses, grounding exercises,
and self-help recommendations tailored to classified user intents and emotions.
"""

from typing import Dict, Any

INTENT_RESPONSES: Dict[str, Dict[str, Any]] = {
    "ANXIETY OR PANIC ATTACK": {
        "reply": (
            "It sounds like you're experiencing anxiety or panic right now. "
            "When anxiety strikes, slowing down your breath helps calm your nervous system. "
            "Try the **4-7-8 Breathing Technique**:\n"
            "1. Inhale quietly through your nose for **4 seconds**.\n"
            "2. Hold your breath for **7 seconds**.\n"
            "3. Exhale slowly through your mouth for **8 seconds**.\n\n"
            "Repeat this cycle 4 times. Remember, you are safe, and this intense feeling will pass."
        ),
        "grounding_exercise": "5-4-3-2-1 Sensory Grounding: Name 5 things you can see around you, 4 things you can physically touch, 3 things you hear, 2 things you smell, and 1 thing you taste.",
        "category": "Anxiety & Panic"
    },
    "STRESS OR PROBLEM": {
        "reply": (
            "Managing high stress levels can feel overwhelming. "
            "Breaking large problems into smaller, actionable steps and scheduling short breaks "
            "can give your mind room to recharge. Remember to focus only on what is within your immediate control today."
        ),
        "grounding_exercise": "Physiological Sigh: Take two quick inhales through your nose, followed by one long, slow exhale through your mouth. Repeat 3 times.",
        "category": "Stress Management"
    },
    "GRIEF OR SADNESS": {
        "reply": (
            "I hear how heavy things feel for you right now. It is completely valid to grieve or feel sad. "
            "Treating yourself with gentle kindness, taking a short walk outdoors, or writing down your feelings "
            "can provide comfort during tough moments."
        ),
        "grounding_exercise": "Place your hand gently over your heart, take three slow deep breaths, and remind yourself: 'I am taking things one moment at a time.'",
        "category": "Emotional Comfort"
    },
    "SLEEP OR FATIGUE ISSUE": {
        "reply": (
            "Restful sleep is essential for physical and mental well-being. "
            "To help your body transition into sleep:\n"
            "• Turn off bright screens 30 minutes before bed.\n"
            "• Practice progressive muscle relaxation (tensing and releasing muscles from toes to face).\n"
            "• Keep your bedroom quiet, dark, and cool."
        ),
        "grounding_exercise": "Body Scan: Close your eyes, lie comfortably, and bring full attention to the physical sensation of your body resting against the surface.",
        "category": "Sleep & Fatigue"
    },
    "SOCIAL LONELINESS": {
        "reply": (
            "Feeling lonely can be deeply painful, but please remember that feeling isolated does not mean you are alone. "
            "Reaching out to a friend, family member, support group, or online community can help rebuild connection."
        ),
        "grounding_exercise": "Consider sending a simple text message to someone you care about or writing a journal entry about a memory that brought you warmth.",
        "category": "Social Connection"
    },
    "MEDITATION OR COPING REQUEST": {
        "reply": (
            "Here is a simple **Box Breathing Exercise** you can do right now:\n\n"
            "1. **Inhale** slowly for 4 seconds.\n"
            "2. **Hold** your breath for 4 seconds.\n"
            "3. **Exhale** for 4 seconds.\n"
            "4. **Hold empty** for 4 seconds.\n\n"
            "Doing this for 2 to 3 minutes lowers stress hormones and restores mental clarity."
        ),
        "grounding_exercise": "Focus your full attention on counting each breath cycle while letting your shoulders drop and relax.",
        "category": "Mindfulness"
    },
    "PHYSICAL OR DAILY NEED": {
        "reply": (
            "Listening to your body's physical needs is essential! "
            "Taking time to eat a nourishing meal, drink water, or take a short rest "
            "directly supports your mood and cognitive focus."
        ),
        "grounding_exercise": "Mindful Refresh: Drink a glass of water slowly, paying attention to the temperature and sensation of every sip.",
        "category": "Self-Care & Daily Needs"
    },
    "SEEKING PROFESSIONAL SUPPORT": {
        "reply": (
            "Reaching out to a qualified mental health professional (such as a licensed therapist, counselor, or doctor) "
            "is one of the most effective steps you can take for your well-being. "
            "Professionals provide personalized evidence-based guidance in a safe environment."
        ),
        "grounding_exercise": "Write down 2-3 specific questions or feelings you would like to discuss during a professional appointment.",
        "category": "Professional Care"
    },
    "GREETING OR CASUAL CHAT": {
        "reply": (
            "Hello! I am MindGuard, your AI mental health & emotional support companion. "
            "I'm here to listen, offer self-help strategies, or guide you through relaxation exercises. "
            "How are you feeling today?"
        ),
        "grounding_exercise": None,
        "category": "General Conversation"
    },
    "BOT INFORMATION REQUEST": {
        "reply": (
            "I am **MindGuard**, an AI conversational companion designed to support mental well-being. "
            "I can assist you with mood tracking, evidence-based self-help coping tools (CBT & Mindfulness exercises), "
            "and immediate emergency helpline information. Please note that I am an automated AI tool and not a substitute for professional medical therapy."
        ),
        "grounding_exercise": None,
        "category": "Information"
    },
    "POSITIVE FEEDBACK": {
        "reply": "I'm so glad to hear that this has been helpful for you. Taking time for self-care and reflection is a great step forward.",
        "grounding_exercise": None,
        "category": "Positive Feedback"
    },
    "NEGATIVE FEEDBACK": {
        "reply": (
            "Thank you for sharing your honest feedback. I am continuously learning and here to support you in whatever way works best for you. "
            "Please let me know if you would like to explore a different topic or try a relaxation exercise."
        ),
        "grounding_exercise": "Take a slow, deep breath in and exhale gently to release any tension.",
        "category": "Feedback & Support"
    },
    "POSITIVE MOOD": {
        "reply": "It is wonderful that you are feeling good today! Celebrating positive moments and noticing what brings you joy can help sustain your well-being.",
        "grounding_exercise": "Notice where you feel warmth or lightness in your body and take a moment to savor it.",
        "category": "Positive Reflection"
    },
    "NEGATIVE MOOD": {
        "reply": (
            "I hear how challenging things feel right now. It is completely normal to have days that feel heavy or draining. "
            "Remember to be gentle with yourself today, one small step at a time."
        ),
        "grounding_exercise": "Place a hand over your chest, take a slow deep breath, and remind yourself: 'I am doing the best I can right now.'",
        "category": "Emotional Comfort"
    },
    "GOODBYE": {
        "reply": "Take good care of yourself. I am here whenever you want to check in again. Have a peaceful day ahead!",
        "grounding_exercise": None,
        "category": "Closing"
    },
    "HUMOR REQUEST": {
        "reply": "Why did the scarecrow win an award? Because he was outstanding in his field! 😊 Taking a lighthearted moment can be a nice break for your mind.",
        "grounding_exercise": None,
        "category": "Lighthearted Break"
    },
    "RELUCTANCE OR CHANGE TOPIC": {
        "reply": (
            "I completely respect that. We can talk about whatever you feel comfortable with, or we can switch to something lighter or try a quiet breathing exercise. "
            "What would you prefer?"
        ),
        "grounding_exercise": None,
        "category": "Boundary & Comfort"
    },
    "PHYSICAL OR DAILY NEED LIKE EATING OR RESTING": {
        "reply": (
            "Listening to your body's physical needs is essential! "
            "Taking time to eat a nourishing meal, drink water, or take a short rest "
            "directly supports your mood and cognitive focus."
        ),
        "grounding_exercise": "Mindful Refresh: Drink a glass of water slowly, paying attention to the temperature and sensation of every sip.",
        "category": "Self-Care & Daily Needs"
    }
}

DEFAULT_FALLBACK_RESPONSE = {
    "reply": (
        "Thank you for sharing that with me. I am here listening. "
        "It can really help to put your feelings into words. "
        "Would you like to try a quick 2-minute relaxation exercise, or share more about what's on your mind?"
    ),
    "grounding_exercise": "Take a slow deep breath in through your nose, hold for 3 seconds, and exhale completely.",
    "category": "Supportive Listening"
}

def get_response_for_intent(intent_label: str, emotion_label: str = None) -> Dict[str, Any]:
    """
    Retrieves formatted psychoeducational response based on intent & emotion.
    """
    normalized_intent = intent_label.upper().strip() if intent_label else ""
    
    matched_response = None
    for key, val in INTENT_RESPONSES.items():
        if key in normalized_intent or normalized_intent in key:
            matched_response = val.copy()
            break

    if not matched_response:
        matched_response = DEFAULT_FALLBACK_RESPONSE.copy()

    if emotion_label and emotion_label.lower() in ["sadness", "fear", "anger"]:
        matched_response["emotion_note"] = f"I notice you may be feeling some {emotion_label.lower()}. Remember it's okay to feel this way."

    return matched_response
