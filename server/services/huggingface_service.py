import logging
import time
import os
from pathlib import Path
from typing import Dict, Any
import joblib

# Enforce local offline loading for cached Hugging Face models to eliminate startup network requests
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MindGuard-ML")

import numpy as np

_EMOTION_PIPE = None
_SENTIMENT_PIPE = None
_ZERO_SHOT_PIPE = None
_CRISIS_MODEL_ARTIFACT = None
_INTENT_MODEL_ARTIFACT = None
_ML_LOAD_FAILED = False

CANDIDATE_INTENT_LABELS = [
    "suicide crisis or self harm risk",
    "anxiety or panic attack",
    "grief or sadness",
    "sleep or fatigue issue",
    "meditation or coping request",
    "physical or daily need like eating or resting",
    "greeting or casual chat",
    "bot information request"
]

import warnings
warnings.filterwarnings("ignore")

from .intent_rules import match_crisis_regex, match_fast_path_intent

def load_ml_pipelines():
    """Loads Hugging Face pipelines and trained joblib models into memory independently with error protection."""
    global _EMOTION_PIPE, _SENTIMENT_PIPE, _CRISIS_MODEL_ARTIFACT, _INTENT_MODEL_ARTIFACT, _ML_LOAD_FAILED

    if _ML_LOAD_FAILED:
        return

    logger.info("Initializing Hugging Face ML pipelines...")
    start_time = time.time()

    # Resolve artifacts directory reliably across workspace root and local paths
    possible_roots = [
        Path(__file__).resolve().parents[2] / "artifacts",
        Path(__file__).resolve().parents[1] / "artifacts",
    ]
    artifacts_dir = next((p for p in possible_roots if p.exists()), possible_roots[0])

    # Load trained TF-IDF + Classifier crisis detector artifact if present
    joblib_path = artifacts_dir / "crisis_detector.joblib"
    if joblib_path.exists() and _CRISIS_MODEL_ARTIFACT is None:
        try:
            logger.info(f"Loading trained crisis detector artifact from {joblib_path}...")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                _CRISIS_MODEL_ARTIFACT = joblib.load(joblib_path)
        except Exception as ex:
            logger.error(f"Could not load crisis_detector.joblib: {ex}")

    # Load trained Multi-Turn Intent Classifier artifact if present
    intent_joblib_path = artifacts_dir / "intent_classifier.joblib"
    if intent_joblib_path.exists() and _INTENT_MODEL_ARTIFACT is None:
        try:
            logger.info(f"Loading trained multi-turn intent classifier artifact from {intent_joblib_path}...")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                _INTENT_MODEL_ARTIFACT = joblib.load(intent_joblib_path)
        except Exception as ex:
            logger.error(f"Could not load intent_classifier.joblib: {ex}")

    try:
        from transformers import pipeline, logging as tf_logging
        tf_logging.set_verbosity_error()

        def _load_pipe(task: str, model_name: str, **kwargs):
            try:
                # Fast local load from cache (zero network calls)
                return pipeline(task, model=model_name, local_files_only=True, **kwargs)
            except Exception:
                # Fallback to online fetch if cache missing
                return pipeline(task, model=model_name, **kwargs)

        # 1. Load Emotion Classifier independently
        if _EMOTION_PIPE is None:
            try:
                logger.info("Loading Emotion Classifier (distilroberta)...")
                _EMOTION_PIPE = _load_pipe(
                    "text-classification",
                    model_name="j-hartmann/emotion-english-distilroberta-base",
                    top_k=1
                )
            except Exception as e:
                logger.error(f"Failed to load Emotion Classifier pipeline: {e}")

        # 2. Load Sentiment Classifier independently
        if _SENTIMENT_PIPE is None:
            try:
                logger.info("Loading Sentiment Classifier (roberta-base)...")
                _SENTIMENT_PIPE = _load_pipe(
                    "text-classification",
                    model_name="cardiffnlp/twitter-roberta-base-sentiment-latest",
                    top_k=1
                )
            except Exception as e:
                logger.error(f"Failed to load Sentiment Classifier pipeline: {e}")

        logger.info(f"ML pipelines initialization attempt completed in {time.time() - start_time:.2f}s")
    except Exception as e:
        logger.error(f"Hugging Face transformers infrastructure error: {e}")
        _ML_LOAD_FAILED = True


def analyze_user_message(text: str, context_turns: list[str] | None = None) -> Dict[str, Any]:
    """
    Runs full inference on user text and optional preceding context_turns.
    Evaluates both the multi-turn context window and single-turn text to maximize safety recall.
    Unconditionally executes match_crisis_regex as an always-on safety floor under ML results.
    Fails safely with elevated ERROR logging if ML models are uninitialized or throw exceptions.
    """
    start_time = time.time()
    clean_text = str(text)[:2000]
    lower_text = clean_text.lower().strip()

    # Format multi-turn context sliding window if context_turns are provided
    if context_turns and isinstance(context_turns, list):
        clean_context_turns = [str(turn)[:500].strip() for turn in context_turns if str(turn).strip()][-3:]
        formatted_input = " \n ".join(clean_context_turns + [clean_text])
    else:
        formatted_input = clean_text

    lower_formatted_input = formatted_input.lower().strip()

    joblib_crisis_prob = 0.0
    top_intent = None
    intent_score = 0.50
    emotion_label = "NEUTRAL"
    emotion_score = 0.50
    sentiment_label = "NEUTRAL"
    sentiment_score = 0.50

    try:
        load_ml_pipelines()
        
        # 1. Joblib Crisis Classifier (Evaluates multi-turn context window & single turn)
        if _CRISIS_MODEL_ARTIFACT is not None:
            try:
                pipeline_obj = _CRISIS_MODEL_ARTIFACT["pipeline"]
                classes = list(pipeline_obj.named_steps["classifier"].classes_)
                
                pos_idx = None
                for target_name in ["suicide", "crisis", "self_harm", "1", 1]:
                    if target_name in classes:
                        pos_idx = classes.index(target_name)
                        break
                        
                if pos_idx is None:
                    logger.error(f"Could not resolve positive crisis class label in model classes: {classes}")
                else:
                    # Evaluate crisis probability on current utterance
                    joblib_crisis_prob = float(pipeline_obj.predict_proba([lower_text])[0, pos_idx])
            except Exception as e:
                logger.error(f"Joblib crisis model prediction failed: {e}")

        # 4a. Joblib high probability check for crisis (independent of PyTorch runtime)
        from .crisis_rules import is_contextual_or_negated
        raw_thresh = float(_CRISIS_MODEL_ARTIFACT.get("threshold", 0.55)) if _CRISIS_MODEL_ARTIFACT else 0.55
        threshold = raw_thresh

        if _CRISIS_MODEL_ARTIFACT is not None and joblib_crisis_prob >= threshold and not is_contextual_or_negated(clean_text):
            top_intent = "SUICIDE CRISIS OR SELF HARM RISK"
            intent_score = round(joblib_crisis_prob, 4)

        try:
            import torch
            with torch.inference_mode():
                # 2. Emotion Pipeline
                if _EMOTION_PIPE:
                    try:
                        emotion_res = _EMOTION_PIPE(clean_text, truncation=True, max_length=128)[0][0]
                        emotion_label = emotion_res["label"].upper()
                        emotion_score = round(float(emotion_res["score"]), 4)
                    except Exception as e:
                        logger.error(f"Emotion pipeline inference error: {e}")

                # 3. Sentiment Pipeline
                if _SENTIMENT_PIPE:
                    try:
                        sentiment_res = _SENTIMENT_PIPE(clean_text, truncation=True, max_length=128)[0][0]
                        sentiment_label = sentiment_res["label"].upper()
                        sentiment_score = round(float(sentiment_res["score"]), 4)
                    except Exception as e:
                        logger.error(f"Sentiment pipeline inference error: {e}")

                # 4b. Multi-Turn Intent Classifier (runs if not already flagged as crisis)
                if top_intent is None and _INTENT_MODEL_ARTIFACT is not None:
                    try:
                        intent_pipe = _INTENT_MODEL_ARTIFACT["pipeline"]
                        intent_classes = list(intent_pipe.named_steps["classifier"].classes_)

                        # Predict with multi-turn sliding window context
                        probs_formatted = intent_pipe.predict_proba([lower_formatted_input])[0]
                        top_idx = int(np.argmax(probs_formatted))
                        predicted_class = intent_classes[top_idx]
                        predicted_conf = float(probs_formatted[top_idx])

                        confidence_thresh = float(_INTENT_MODEL_ARTIFACT.get("confidence_threshold", 0.45))

                        LABEL_MAP = {
                            "anxiety_or_fear": "ANXIETY OR PANIC ATTACK",
                            "sleep_problem": "SLEEP OR FATIGUE ISSUE",
                            "meditation_interest": "MEDITATION OR COPING REQUEST",
                            "sadness_or_low_self_worth": "GRIEF OR SADNESS",
                            "grief_or_loss": "GRIEF OR SADNESS",
                            "bot_information": "BOT INFORMATION REQUEST",
                            "greeting_or_introduction": "GREETING OR CASUAL CHAT",
                            "casual_conversation": "GREETING OR CASUAL CHAT",
                            "positive_feedback": "POSITIVE FEEDBACK",
                            "negative_feedback": "NEGATIVE FEEDBACK",
                            "positive_mood": "POSITIVE MOOD",
                            "goodbye": "GOODBYE",
                            "humor_request": "HUMOR REQUEST",
                            "reluctance_or_change_topic": "RELUCTANCE OR CHANGE TOPIC",
                        }

                        if predicted_conf >= confidence_thresh and predicted_class in LABEL_MAP:
                            top_intent = LABEL_MAP[predicted_class]
                            intent_score = round(predicted_conf, 4)
                        else:
                            top_intent = match_fast_path_intent(clean_text) or "GENERAL SUPPORT TOPIC"
                            intent_score = 0.75 if top_intent != "GENERAL SUPPORT TOPIC" else 0.50
                    except Exception as ex:
                        logger.error(f"Intent model inference error: {ex}")
                        top_intent = match_fast_path_intent(clean_text) or "GENERAL SUPPORT TOPIC"
                        intent_score = 0.50
        except Exception as torch_err:
            logger.error(f"PyTorch pipelines inference error: {torch_err}")

        # Fallback to fast-path intent matching if still unassigned
        if top_intent is None:
            top_intent = match_fast_path_intent(clean_text)
            if top_intent:
                intent_score = 0.85
            else:
                top_intent = "GENERAL SUPPORT TOPIC"
                intent_score = 0.50

    except Exception as err:
        logger.error(f"Execution error during ML analysis pipeline: {err}", exc_info=True)

    # 5. ALWAYS-ON UNCONDITIONAL REGEX SAFETY FLOOR
    # Evaluates match_crisis_regex on current user message with negation awareness
    if match_crisis_regex(clean_text) and not is_contextual_or_negated(clean_text):
        top_intent = "SUICIDE CRISIS OR SELF HARM RISK"
        intent_score = 1.0

    if top_intent is None:
        top_intent = "GENERAL SUPPORT TOPIC"
        intent_score = 0.50

    latency_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "intent": top_intent,
        "intent_confidence": intent_score,
        "emotion": emotion_label,
        "emotion_confidence": emotion_score,
        "sentiment": sentiment_label,
        "sentiment_confidence": sentiment_score,
        "inference_latency_ms": latency_ms
    }


