"""
Extraction harness — see what the classifier and entity extractor actually do
across a spread of realistic messages. Writes nothing; safe to run repeatedly.

    railway run python3 backend/scripts/test_extraction.py
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from classifier.pillar_classifier import classify_input
from memory.profile_enricher import _should_run_haiku, _haiku_extract

MESSAGES = [
    "I was listening to Mohammed Rafi last night but my back has been aching badly",
    "My knee is hurting again, same as last winter",
    "Shubham called from Bangalore yesterday, he sounded tired",
    "I want to visit Kedarnath before I get too old",
    "The electricity bill was much higher this month, I'm worried",
    "Watched the India match yesterday, Kohli played well",
    "Good morning, how are you today?",
    "Haan theek hai",
    "I take my BP medicine at 9 every night",
    "Made aloo paratha for breakfast today",
]

for msg in MESSAGES:
    print("=" * 78)
    print(msg)
    cl = classify_input(msg)
    run, hint = _should_run_haiku(cl)
    print(f"  core={cl.core}/{cl.core_priority}  emotion={cl.emotion}/{cl.emotion_priority}  extract={run}")
    if run:
        ents = (_haiku_extract(msg, hint) or {}).get("entities", [])
        if ents:
            for e in ents:
                print(f"    -> {e.get('name')!r}  type={e.get('type')}  pillar={e.get('pillar')}")
        else:
            print("    -> (no entities returned)")
