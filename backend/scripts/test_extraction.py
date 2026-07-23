"""
Extraction harness — see what the classifier and entity extractor actually do
across a spread of realistic messages. Writes nothing; safe to run repeatedly.

    railway run python3 backend/scripts/test_extraction.py
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from classifier.pillar_classifier import classify_input, CORE_PILLARS
from memory.profile_enricher import _should_run_haiku, _pillar_guide


def rich_extract(text: str) -> dict:
    """
    Prototype extractor: predicate-style, not just nouns.

    We want the noun AND what happened to it AND how they feel about it —
    "back pain / worsening / negative" is a different signal from
    "back pain / improving / positive", and counting them the same way
    would make the recommendation engine confidently wrong.
    """
    guide, names = _pillar_guide()
    options = "|".join(names)

    prompt = f"""Extract what this person is telling you about.

Pillar definitions:
{guide}

Message: "{text}"

For each specific thing mentioned, return:
- name: the thing itself, stripped of connectors ("the", "a", "my"). Noun form.
- action: what happened to it or what they did with it, as a single verb or short verb phrase
- sentiment: positive | negative | neutral — how THEY feel about it
- salience: 0.0-1.0 — how much this matters to them right now
- type: person|artist|hobby|health|place|food|media|activity|other
- pillar: {options}

Return ONLY JSON: {{"entities": [...]}}
Empty list if nothing specific is mentioned. Do not invent things.

Examples:
"I was listening to Mohammed Rafi but my back has been aching badly"
{{"entities": [
  {{"name": "Mohammed Rafi", "action": "listened", "sentiment": "positive", "salience": 0.6, "type": "artist", "pillar": "ENTERTAINMENT"}},
  {{"name": "back pain", "action": "worsening", "sentiment": "negative", "salience": 0.9, "type": "health", "pillar": "HEALTH_WELLNESS"}}
]}}

"I don't really enjoy Kishore Kumar songs"
{{"entities": [{{"name": "Kishore Kumar", "action": "disliked", "sentiment": "negative", "salience": 0.5, "type": "artist", "pillar": "ENTERTAINMENT"}}]}}
"""
    try:
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        resp = client.models.generate_content(
            model="gemini-flash-lite-latest", contents=prompt)
        raw = (resp.text or "").strip().replace("```json", "").replace("```", "").strip()
        return json.loads(raw) if raw else {}
    except Exception as e:
        print(f"    !! extraction error: {e}")
        return {}

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
    # negative sentiment — must NOT read as interest
    "I really don't enjoy these new Bollywood songs, too much noise",
    "My knee is much better this week, the exercises are helping",
    "I hate going to the hospital, always so crowded",
    # ambiguous / mixed
    "Shubham hasn't called in two weeks",
]

for msg in MESSAGES:
    print("=" * 78)
    print(msg)
    cl = classify_input(msg)
    run, hint = _should_run_haiku(cl)
    print(f"  core={cl.core}/{cl.core_priority}  emotion={cl.emotion}/{cl.emotion_priority}  extract={run}")
    if run:
        ents = (rich_extract(msg) or {}).get("entities", [])
        if ents:
            for e in ents:
                print(f"    -> {str(e.get('name')):22} {str(e.get('action')):14} "
                      f"{str(e.get('sentiment')):9} sal={e.get('salience')} "
                      f"{e.get('pillar')}")
        else:
            print("    -> (no entities returned)")
