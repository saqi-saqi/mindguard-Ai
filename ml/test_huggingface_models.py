"""
MindGuard - HuggingFace Model Evaluation & Benchmark Script
------------------------------------------------------------
This script tests pre-trained Hugging Face Transformer models for:
1. Emotion Analysis (DistilRoBERTa 7-emotion)
2. Sentiment Classification (RoBERTa Sentiment)
3. Zero-Shot Intent & Crisis Triage (DistilBART MNLI)
"""

import sys
import time

try:
    import torch
    from transformers import pipeline
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False



# Sample test sentences representing real user conversations & edge cases
TEST_SAMPLES = [
    # Crisis / High-risk examples
    "I feel so overwhelmed and hopeless. I don't want to wake up tomorrow.",
    "Everything is hurting me and I can't take this pain anymore. I want to end my life.",
    "I am thinking of harming myself tonight.",
    
    # False alarm / Negation examples (TF-IDF usually fails these!)
    "I am NOT feeling suicidal, just tired after a long work day.",
    "My friend told me a story about suicide in a movie.",
    "I used to feel depressed years ago, but now I'm feeling great and happy!",

    # Emotion & Stress examples
    "I have an exam tomorrow and I'm feeling really anxious and stressed out.",
    "I lost my job today and I feel completely broken and sad.",

    # Casual / Neutral / Intent examples
    "Hello! How can you help me today?",
    "Can you recommend some breathing exercises or meditation techniques?",
    "What is your name and who created you?",
]

def test_emotion_detection():
    print("\n=======================================================")
    print(" 1. EMOTION CLASSIFIER (j-hartmann/emotion-english-distilroberta-base)")
    print("=======================================================")
    
    try:
        emotion_pipe = pipeline(
            "text-classification",
            model="j-hartmann/emotion-english-distilroberta-base",
            return_all_scores=False
        )
        
        for text in TEST_SAMPLES[:6]:
            res = emotion_pipe(text)[0]
            print(f"\nInput: \"{text}\"")
            print(f" -> Predicted Emotion: {res['label'].upper()} (Score: {res['score']:.4f})")
            
    except Exception as e:
        print(f"[!] Could not run emotion model: {e}")


def test_sentiment_analysis():
    print("\n=======================================================")
    print(" 2. SENTIMENT CLASSIFIER (cardiffnlp/twitter-roberta-base-sentiment-latest)")
    print("=======================================================")
    
    try:
        sentiment_pipe = pipeline(
            "text-classification",
            model="cardiffnlp/twitter-roberta-base-sentiment-latest",
            return_all_scores=False
        )
        
        for text in TEST_SAMPLES[3:8]:
            res = sentiment_pipe(text)[0]
            print(f"\nInput: \"{text}\"")
            print(f" -> Predicted Sentiment: {res['label'].upper()} (Score: {res['score']:.4f})")
            
    except Exception as e:
        print(f"[!] Could not run sentiment model: {e}")


def test_zero_shot_intents():
    print("\n=======================================================")
    print(" 3. ZERO-SHOT INTENT & TRIAGE CLASSIFIER (valhalla/distilbart-mnli-12-3)")
    print("=======================================================")
    
    candidate_labels = [
        "suicide crisis or self harm risk",
        "anxiety or panic attack",
        "grief or sadness",
        "sleep or fatigue issue",
        "meditation or coping request",
        "greeting or casual chat",
        "bot information request"
    ]
    
    try:
        zero_shot_pipe = pipeline(
            "zero-shot-classification",
            model="valhalla/distilbart-mnli-12-3"
        )
        
        for text in TEST_SAMPLES:
            res = zero_shot_pipe(text, candidate_labels)
            top_label = res['labels'][0]
            top_score = res['scores'][0]
            print(f"\nInput: \"{text}\"")
            print(f" -> Top Intent/Category: [{top_label.upper()}] (Score: {top_score:.4f})")
            
    except Exception as e:
        print(f"[!] Could not run zero-shot model: {e}")


if __name__ == "__main__":
    print("=======================================================")
    print("      MINDGUARD HUGGINGFACE MODEL BENCHMARK TEST      ")
    print("=======================================================")
    start_time = time.time()
    
    test_emotion_detection()
    test_sentiment_analysis()
    test_zero_shot_intents()
    
    elapsed = time.time() - start_time
    print(f"\n[DONE] Benchmark complete in {elapsed:.2f} seconds.")
