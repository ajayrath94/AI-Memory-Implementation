"""
EMBEDDING CLASSIFIER TEST SUITE
Tests classification accuracy and cosine similarity scores.
Run after centroids are built.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, '/Users/ajayrath/Documents/GitHub/AI-Memory-Implementation/backend')

# ── Test cases ─────────────────────────────────────────────────────────────────

TEST_CASES = [
    # (text, expected_core, expected_emotion, expected_functional, description)

    # English health
    ("My knee has been hurting badly",           "HEALTH_WELLNESS", "STRESS",   "CHAT",   "Health English"),
    ("Blood pressure is very high today",        "HEALTH_WELLNESS", "FEAR",     "CHAT",   "BP concern"),
    ("I need to take my medicine",               "HEALTH_WELLNESS", "NEUTRAL",  "NUDGE",  "Medicine reminder"),
    ("Doctor visit is tomorrow",                 "HEALTH_WELLNESS", "NEUTRAL",  "PLAN",   "Doctor plan"),
    ("I cannot sleep at night at all",           "HEALTH_WELLNESS", "STRESS",   "CHAT",   "Sleep problem"),

    # Hindi health
    ("Ghutne mein bahut dard hai",               "HEALTH_WELLNESS", "STRESS",   "CHAT",   "Knee pain Hindi"),
    ("BP badha hua hai aaj",                     "HEALTH_WELLNESS", "FEAR",     "CHAT",   "BP Hindi"),
    ("Dawai lena bhool gayi",                    "HEALTH_WELLNESS", "NEUTRAL",  "NUDGE",  "Medicine Hindi"),
    ("Doctor ke paas jaana hai",                 "HEALTH_WELLNESS", "NEUTRAL",  "PLAN",   "Doctor Hindi"),

    # Entertainment
    ("I want to watch a movie tonight",          "ENTERTAINMENT",   "OPTIMISM", "SEARCH", "Movie English"),
    ("Cricket match is today",                   "ENTERTAINMENT",   "OPTIMISM", "CHAT",   "Cricket English"),
    ("Cricket ka match hai aaj",                 "ENTERTAINMENT",   "OPTIMISM", "CHAT",   "Cricket Hindi"),
    ("Purane gaane sunna chahta hoon",           "ENTERTAINMENT",   "NEUTRAL",  "CHAT",   "Music Hindi"),

    # Finance
    ("My pension has not arrived yet",           "FINANCE",         "STRESS",   "TRACK",  "Pension English"),
    ("Paisa khatam ho raha hai",                 "FINANCE",         "STRESS",   "CHAT",   "Finance Hindi"),
    ("Bijli ka bill bahut aaya",                 "FINANCE",         "ANGER",    "CHAT",   "Bill Hindi"),

    # Emotions
    ("I am so happy today my son visited",       "GENERAL",         "JOY",      "CHAT",   "Joy English"),
    ("Bahut dukh ho raha hai aaj",               "GENERAL",         "SADNESS",  "CHAT",   "Sadness Hindi"),
    ("Bahut tension hai ghar mein",              "GENERAL",         "STRESS",   "CHAT",   "Stress Hindi"),
    ("Bahut gussa aa raha hai",                  "GENERAL",         "ANGER",    "CHAT",   "Anger Hindi"),

    # API triggers
    ("Mujhe achha nahi lag raha emergency hai",  "HEALTH_WELLNESS", "FEAR",     "CHAT",   "Emergency"),
    ("Dawai yaad dilao mujhe",                   "HEALTH_WELLNESS", "NEUTRAL",  "NUDGE",  "Medicine reminder"),
    ("Cricket score kya hai",                    "ENTERTAINMENT",   "NEUTRAL",  "SEARCH", "Cricket score"),
    ("Beta se baat karni hai video call",        "GENERAL",         "JOY",      "ORDER",  "Family call"),
    ("Aaj barish hogi kya",                      "GENERAL",         "NEUTRAL",  "SEARCH", "Weather check"),
]

def run_tests():
    from classifier.pillar_classifier import classify_input

    print("=" * 70)
    print("🧠 NANCY EMBEDDING CLASSIFIER TEST SUITE")
    print("=" * 70)

    core_correct     = 0
    emotion_correct  = 0
    func_correct     = 0
    total            = len(TEST_CASES)
    low_confidence   = []
    wrong_core       = []

    for text, exp_core, exp_emotion, exp_func, desc in TEST_CASES:
        result = classify_input(text)

        core_ok    = result.core == exp_core
        emotion_ok = result.emotion == exp_emotion
        func_ok    = result.functional == exp_func

        if core_ok:    core_correct += 1
        if emotion_ok: emotion_correct += 1
        if func_ok:    func_correct += 1

        score_pct = round(result.core_score * 100)
        status    = "✅" if core_ok else "❌"

        print(f"\n{status} [{desc}]")
        print(f"   Input:    {text}")
        print(f"   Core:     {result.core} ({score_pct}%) {'✅' if core_ok else f'❌ expected {exp_core}'}")
        print(f"   Emotion:  {result.emotion} {'✅' if emotion_ok else f'❌ expected {exp_emotion}'}")
        print(f"   Intent:   {result.functional} {'✅' if func_ok else f'❌ expected {exp_func}'}")
        print(f"   Language: {result.language}")
        if result.api_triggers:
            print(f"   Triggers: {result.api_triggers}")

        # Top pillar scores
        scores = sorted(result.pillar_scores.items(), key=lambda x: x[1], reverse=True)[:3]
        print(f"   Top scores: {scores}")

        if score_pct < 40:
            low_confidence.append((desc, text, score_pct))
        if not core_ok:
            wrong_core.append((desc, text, exp_core, result.core, score_pct))

    # ── Summary ──
    print("\n" + "=" * 70)
    print("📊 RESULTS SUMMARY")
    print("=" * 70)
    print(f"Core accuracy:     {core_correct}/{total}  = {round(core_correct/total*100)}%")
    print(f"Emotion accuracy:  {emotion_correct}/{total} = {round(emotion_correct/total*100)}%")
    print(f"Intent accuracy:   {func_correct}/{total}  = {round(func_correct/total*100)}%")

    overall = (core_correct + emotion_correct + func_correct) / (total * 3)
    print(f"\nOverall accuracy:  {round(overall*100)}%")

    if wrong_core:
        print(f"\n❌ Wrong core classifications ({len(wrong_core)}):")
        for desc, text, expected, got, score in wrong_core:
            print(f"  [{desc}] Expected {expected}, got {got} ({score}%)")
            print(f"  Text: {text}")

    if low_confidence:
        print(f"\n⚠️  Low confidence (<40%) classifications ({len(low_confidence)}):")
        for desc, text, score in low_confidence:
            print(f"  [{desc}] {score}% — {text[:50]}")

    print("\n" + "=" * 70)

    # Grade
    pct = round(overall * 100)
    if pct >= 85:
        grade = "🏆 EXCELLENT — Production ready!"
    elif pct >= 70:
        grade = "✅ GOOD — Minor improvements needed"
    elif pct >= 55:
        grade = "⚠️  FAIR — Add more examples per pillar"
    else:
        grade = "❌ NEEDS WORK — Check centroid quality"

    print(f"Grade: {grade}")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
