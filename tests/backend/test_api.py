"""
MindGuard - Backend API Integration Test Script
-----------------------------------------------
Sends sample user requests to http://127.0.0.1:5000/api/chat to verify
the API, crisis triage, ML classification, and JSON payloads.
"""

import sys
import time
import requests

API_URL = "http://127.0.0.1:5000/api/chat"

TEST_CASES = [
    "Hello! How can you help me today?",
    "I am feeling so stressed out and anxious about my exam tomorrow.",
    "I lost my job today and I feel completely broken and sad.",
    "I am NOT feeling suicidal, just tired after a long work day.",
    "Everything is hurting me and I can't take this pain anymore. I want to end my life.",
]

def run_api_tests():
    print("=======================================================")
    print("        TESTING MINDGUARD FLASK REST API             ")
    print("=======================================================")
    
    for text in TEST_CASES:
        print(f"\n[USER MESSAGE]: \"{text}\"")
        try:
            res = requests.post(API_URL, json={"message": text}, timeout=10)
            if res.status_code == 200:
                data = res.json()
                print(f" -> Risk Level: {data.get('risk_level')}")
                print(f" -> Intent:     {data.get('intent')} (Score: {data.get('intent_confidence')})")
                print(f" -> Emotion:    {data.get('emotion')}")
                print(f" -> Sentiment:  {data.get('sentiment')}")
                print(f" -> Bot Reply:  \n{data.get('reply')[:150]}...")
            else:
                print(f" [!] API Error {res.status_code}: {res.text}")
        except Exception as e:
            print(f" [!] Connection Error: {e}")

if __name__ == "__main__":
    run_api_tests()
