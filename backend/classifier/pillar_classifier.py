"""
EMBEDDING CLASSIFIER v3
Pure Google text-embedding-004 (free, great for Hindi + English)
No Voyage AI dependency.
"""

import os
import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

CORE_PILLARS       = ["FINANCE","ASPIRATIONS","CAREER_GOAL","HEALTH_WELLNESS","ENTERTAINMENT","GENERAL"]
EMOTION_PILLARS    = ["OPTIMISM","JOY","FEAR","SADNESS","ANGER","STRESS","NEUTRAL"]
FUNCTIONAL_PILLARS = ["PLAN","SEARCH","ORDER","TRACK","NUDGE","CHAT"]
MODIFIER_PILLARS   = ["QUANTITY","SPECIFICITY","FORMAT","LOCATION","EXCLUSION","URGENCY","CONDITION","PREFERENCE","TEMPORAL","COMPARISON"]
DIMENSION_ORDER    = CORE_PILLARS + EMOTION_PILLARS + FUNCTIONAL_PILLARS + MODIFIER_PILLARS

PILLAR_EXAMPLES = {
    "FINANCE": [
        "I'm worried about my savings","My pension is late this month","How should I manage my budget?",
        "The electricity bill is too high","I need to send money to my son","My fixed deposit is maturing",
        "Worried about hospital expenses","My bank balance is low","Need to check my account",
        "Paisa khatam ho raha hai","Pension nahi aayi abhi tak","Bijli ka bill bahut aaya",
        "Bacchon ko paisa bhejana hai","Bank mein paise kam hain","Mera budget tight hai",
        "Savings bahut kam hai","Ghar ka kharcha bahut hai","Hospital ka bill aaya",
        "Cost of medicines is rising","Need to save more money","My expenses are too high",
        "Loan EMI is due","Investment returns are low","UPI se bhejdo paise",
        "Mobile recharge karna hai","Gas cylinder ka bill","Property tax due hai",
    ],
    "HEALTH_WELLNESS": [
        "My knee has been hurting","I cannot sleep properly","Blood pressure is high today",
        "I need to take my medicine","Feeling tired all the time","Chest feels a bit tight",
        "My back is aching badly","Doctor visit tomorrow","Sugar level is not controlled",
        "Ghutne mein bahut dard hai","Neend nahi aati raat ko","BP badha hua hai",
        "Dawai lena bhool gayi","Bahut thakaan ho rahi hai","Seene mein dard hai",
        "Kamar dard se pareshan hoon","Doctor ke paas jaana hai","Sugar control nahi ho rahi",
        "Breathing problem ho rahi","Aankhein kamzor ho gayi","Chalne mein takleef",
        "Haath kaanpte hain","Sar dard rehta hai","Pet mein dard hai","Acidity ki problem",
        "Diabetes hai mujhe","Heart problem hai","Arthritis hai","Thyroid ki problem",
    ],
    "ENTERTAINMENT": [
        "I want to watch a movie","Cricket match is today","Favorite song is playing",
        "Old Hindi movies are best","Love watching serials","Reading newspaper daily",
        "Playing cards with friends","Watching cricket on TV","Movie dekhni hai aaj",
        "Cricket ka match hai","Purane gaane sunna chahta","TV serial achha hai",
        "Kitaab padh raha hoon","Bollywood news dekhna","Sports channel lagao",
        "India vs Pakistan match","IPL exciting hai","Rohit sharma ka shot",
        "Lata mangeshkar songs","Kishore kumar gaane","Mohammed rafi classic",
        "Old Bollywood films","Amitabh bachchan movies","Comedy shows on TV",
        "Bhajan kirtan","Drama serial following","Music competition shows",
    ],
    "ASPIRATIONS": [
        "I want to travel before I die","My dream is to visit Varanasi",
        "I hope my grandchildren do well","I want to learn something new",
        "My goal is to stay healthy","I wish I could dance again",
        "I want to write my memoirs","Hope to see everyone settled",
        "Mera sapna hai ki main ghoomoon","Bacche settle ho jaayein",
        "Kuch naya seekhna chahta hoon","Life mein kuch aur karna hai",
        "Tirth yatra karni hai","Yoga seekhna chahta hoon",
        "I want to visit my hometown","Wish to meet old friends",
        "Dream of peaceful retirement","Want to learn music",
        "Want to volunteer","Hope to live long","Want to teach children",
    ],
    "CAREER_GOAL": [
        "I used to work as a teacher","My job was very demanding",
        "I retired last year","Miss my colleagues","Work life was different then",
        "I was a government officer","Ran my own business for 30 years",
        "Main teacher tha pehle","Sarkari naukri thi meri","Business kiya tha",
        "Apna dukaan tha","Office mein kaam kiya","Retired ho gaya hoon",
        "Colleagues yaad aate hain","Kaam ki duniya alag thi",
        "Doctor tha main","Nurse thi main pehle","Accountant tha","Engineer tha",
        "Banking career","Government service","Army retired","Police service",
        "I worked hard all my life","Proud of my work","Miss the routine of work",
    ],
    "GENERAL": [
        "How are you today","Good morning","Just wanted to chat","Nothing specific",
        "Kaise ho aap","Subah ki chai","Aaj kya hua","Bas baat karni thi",
        "Kuch khaas nahi","Aam din hai","Normal chal raha","Bas theek hoon",
        "Regular routine","Same as usual","Nothing new","Getting by",
        "Day passing","Time going","Routine completed","No complaints",
        "Just existing","Passing time","Uneventful","Quiet day",
        "Nice weather today","What a day","Random thoughts","Just saying hello",
    ],
    "OPTIMISM": [
        "Feeling great today","Things are looking up","I am excited about tomorrow",
        "Confident everything will work out","Hopeful for better days",
        "Aaj bahut achha lag raha","Kal acha hoga","Positive soch rakhta hoon",
        "Umeed hai mujhe","Achhe din aayenge","Sab theek hoga","Motivated hoon",
        "Happy about future","Great feeling today","Wonderful mood",
        "Feeling blessed","Grateful for life","Good vibes only",
        "Bright future ahead","Things improving","Getting better each day",
        "Family support amazing","God is kind","Bhagwan ka ashirwad",
    ],
    "JOY": [
        "I am so happy today","My grandchildren visited","Wonderful news received",
        "Son called from abroad","Daughter got good news","Family is together",
        "Bahut khush hoon aaj","Beta aa gaya ghar","Beti ki achhi khabar",
        "Pota khelne aaya","Naati ne call kiya","Parivaar saath hai",
        "Shaadi ki anniversary","Birthday celebration","Festival mein mazaa",
        "Old friend met today","Good food today","Favourite dish banaya",
        "Laughed a lot today","Children playing","Grandkids funny","Adorable moment",
        "Feeling loved","Delicious meal","Temple visit","Peaceful prayer",
    ],
    "FEAR": [
        "I am worried about my health","Scared about the future",
        "Anxious about surgery","Nervous about test results","Afraid of falling",
        "Darr lag raha hai","Chinta ho rahi hai","Future ki fikar hai",
        "Operation se darr","Test result ka dar","Akele rehne ki chinta",
        "Ghar mein koi nahi","Raat ko darr lagta","Health deteriorating fear",
        "Uncertain about treatment","Doctor ki baat sunke dara",
        "Children far away","No one to help","Helpless feeling","Vulnerable today",
        "Medical anxiety","Health scare","Financial insecurity","Worried about money",
        "Scared of dying","Fear of pain","Panic moment","Anxiety episode",
    ],
    "SADNESS": [
        "Feeling very sad today","Missing my husband","Spouse passed away",
        "Lonely without family","Children do not call much","Miss the old days",
        "Bahut dukh ho raha hai","Pati yaad aa rahe hain","Patni chali gayi",
        "Akela mehsoos kar raha","Bacche call nahi karte","Purane din yaad aate",
        "Dost nahi rahe","Ghar soona lagta hai","Koi baat karne wala nahi",
        "Depression feeling","Crying today","Heavy heart","Grief overwhelming",
        "Mourning loss","Old memories pain","Missed opportunities","Regrets haunting",
        "Taken for granted","Not valued","Emotional neglect","Isolated",
        "No one cares","Outlived friends","Generation gone","Legacy forgotten",
    ],
    "ANGER": [
        "I am really frustrated today","Children do not listen",
        "Nobody respects elders anymore","Very upset about this","Makes me so angry",
        "Bahut gussa aa raha","Bacche nahi sunte","Budhon ki izzat nahi",
        "Bahut naraaz hoon","Cheat kiya kisi ne","Fraud hua","Money cheated",
        "Betrayed by family","Hurt by words","Disrespected publicly","Humiliated",
        "Argument happened","Fight with family","Not listened to","Dismissed",
        "Medical negligence","Government system bad","Corruption anger",
        "Pension delayed","Rights denied","Traffic jam frustrated","Service bad",
        "Family politics","Property dispute","Inheritance fight","Family drama",
    ],
    "STRESS": [
        "Feeling very stressed today","Too much to handle",
        "Overwhelmed by everything","Cannot sleep from worry",
        "Bahut tension hai","Bahut zyada ho gaya","Sab kuch sambhalna mushkil",
        "Chinta se neend nahi","Ghar mein tension hai","Pressure bohot hai",
        "Exhausted completely","Drained out","No energy left","Cannot cope anymore",
        "Multiple problems at once","Health stress","Financial pressure",
        "Family tension","Caregiver burden","Looking after sick spouse",
        "Managing alone","No support available","Crisis situation",
        "Doctor appointments piling","Tests pending","Insurance claim",
        "Mental load heavy","Decision fatigue","Confused about choices",
    ],
    "NEUTRAL": [
        "Okay I suppose","Nothing special happening","Just a normal day","Fine I guess",
        "Theek hai","Kuch khaas nahi","Aam din hai","Normal chal raha",
        "Bas theek hoon","Middle ground","Neither happy nor sad","Regular routine",
        "Same as usual","Nothing new","Status quo","Managing okay","Surviving",
        "Day passing","Time going","No complaints","No praises","Just existing",
        "Uneventful","Quiet day","Peaceful but boring","Calm but dull",
        "No major changes","Stable condition","Predictable day","As anticipated",
    ],
    "PLAN": [
        "I need to plan my doctor visit","Let me organize my medicines",
        "Need to schedule a call with son","Planning family trip",
        "Doctor appointment plan karna","Dawai ka schedule banana",
        "Beta se baat ka plan","Family trip plan","Agenda banana chahiye",
        "Timetable banana","Weekly plan","Daily routine set karna",
        "Month ka budget plan","Exercise schedule","Diet plan follow karna",
        "Morning routine plan","Evening walk time","Prayer time schedule",
        "Market jao plan","Grocery list banana","House cleaning schedule",
        "Family gathering plan","Birthday party organize","Travel itinerary",
        "Emergency plan","Contingency planning","Long term plan",
    ],
    "SEARCH": [
        "Can you find me a good doctor","Where is the nearest hospital",
        "Recommend a good medicine","What is this disease called",
        "Achha doctor dhundo","Hospital kahan hai","Dawai suggest karo",
        "Yeh bimari kya hai","Kahan milega","Kaise pata karoon",
        "Which hospital is best","Best specialist for","How to find out",
        "Recipe for","How to make","Instructions for","Nearest pharmacy",
        "Medical store location","Bus route to hospital","Bank branch near me",
        "Cricket score","Weather forecast","Train schedule","Movie timing",
        "Festival date","Holiday list","Auspicious date","Pandit contact",
    ],
    "ORDER": [
        "Order my medicines online","Book a doctor appointment",
        "Get groceries delivered","Buy this for me","Purchase the medicine",
        "Dawai order karo","Doctor appointment book karo","Grocery mangao",
        "Online order karo","Delivery mangao","Cab book karo","Ola book karo",
        "Food order karo","Swiggy se mangao","Zomato order","Home delivery",
        "Amazon se mangao","Online shopping","Bill payment karo","Recharge karo",
        "Book movie ticket","Train ticket book","Hotel booking","Resort reservation",
        "Flowers order","Gift order","Plumber call","Electrician call",
    ],
    "TRACK": [
        "Check my blood pressure today","Monitor my sugar levels",
        "Track my medicine intake","Follow up on test results",
        "What was my weight yesterday","Check if son called",
        "BP check karo","Sugar monitor karo","Dawai track karo",
        "Test result follow up","Status check karo","Progress dekho",
        "Update kya hai","Kya result aaya","Medicine reminder check",
        "Did I take medicine","Water intake track","Steps counted today",
        "Exercise done check","Doctor visit history","Medical records",
        "Insurance claim status","Hospital bill status","Delivery status",
        "Bank transaction check","Account balance","Pension credited check",
        "Cricket score update","Match status","Weather update",
    ],
    "NUDGE": [
        "Remind me to take my medicine","Do not let me forget the appointment",
        "Alert me when son calls","Make sure I drink water",
        "Remind me about prayers","Tell me when it is time",
        "Dawai yaad dilao","Appointment mat bhulaana","Beta ka call yaad dilaana",
        "Paani peena yaad dilao","Namaz ka waqt batao","Pooja ka time batao",
        "Remind every day","Daily reminder chahiye","Weekly reminder",
        "Set alarm for","Notification chahiye","Do not forget to",
        "Medicine at 8am reminder","Dinner time reminder","Sleep time reminder",
        "Wake up call","Exercise reminder","Walk time","Prayer time alert",
        "Birthday reminder","Anniversary alert","Follow up reminder","Bill due reminder",
    ],
    "CHAT": [
        "Just want to talk","Tell me a story","Let us have a conversation",
        "I am lonely talk to me","Baat karo mere se","Koi kahani sunao",
        "Baatein karte hain","Akela hoon baat karo","Company chahiye",
        "Kuch batao","Timepass karo","How are you doing","What is new",
        "Nice to talk","Good conversation","You understand me","You listen well",
        "Share my thoughts","Express myself","Vent my feelings","Deep talk",
        "Life discussion","Religion and spirituality","Past experiences share",
        "Life stories","Childhood memories","Old India talk","Recipe discussion",
        "Wisdom sharing","Life lessons","Joke telling","Poetry recitation",
    ],
}

API_TRIGGER_EXAMPLES = {
    "book_doctor": [
        "I need to see a doctor","Book an appointment",
        "Doctor ke paas jaana hai","Hospital appointment chahiye",
        "Specialist dikhana hai","Checkup karwana hai",
        "OPD mein jaana hai","Doctor se milna hai",
    ],
    "play_music": [
        "Play some music","I want to listen to bhajan",
        "Koi gaana lagao","Music sunna hai","Bhajan chalao",
        "Old songs please","Lata ji ka gaana","Kishore kumar songs",
    ],
    "cricket_score": [
        "Cricket score kya hai","India ka match kab hai",
        "IPL mein kaun jeeta","Match chal raha hai kya",
        "Score kya hai abhi","India jeet gaya kya","Batting kaun kar raha",
    ],
    "medicine_reminder": [
        "Dawai yaad dilao","Medicine reminder set karo",
        "BP ki dawai leni hai","Remind me about pills",
        "Dawai lena bhool jaata hoon","Daily medicine alert",
    ],
    "weather_check": [
        "Aaj barish hogi kya","Weather kaisa hai","Bahar kitni garmi hai",
        "Umbrella le jaaoon kya","Temperature kya hai","Mausam kaisa hai aaj",
    ],
    "emergency": [
        "I do not feel well","Mujhe achha nahi lag raha",
        "Call someone please","I need help immediately",
        "Chest mein dard hai","Bahut dard ho raha","Breathing problem",
        "Emergency hai","Help chahiye abhi",
    ],
    "call_family": [
        "I want to call my son","Beta se baat karni hai",
        "Beti ko call karo","Family se baat karo",
        "Video call karo bacchon se","Whatsapp call lagao",
    ],
}

API_THRESHOLDS = {
    "emergency":         0.82,
    "book_doctor":       0.75,
    "call_family":       0.72,
    "medicine_reminder": 0.70,
    "cricket_score":     0.68,
    "weather_check":     0.65,
    "play_music":        0.63,
}

_centroid_cache: Dict[str, List[float]] = {}
_api_trigger_cache: Dict[str, List[float]] = {}


# ── Language detection ─────────────────────────────────────────────────────────

def _detect_language(text: str) -> str:
    hindi_chars = set('अआइईउऊएऐओऔकखगघचछजझटठडढणतथदधनपफबभमयरलवशषसह')
    if any(c in hindi_chars for c in text):
        return "hi"
    hinglish = ["hai","hoon","karo","nahi","aaj","kal","mera","meri",
                "mere","aap","tum","main","beta","beti","dadi","nana"]
    if any(w in text.lower().split() for w in hinglish):
        return "hi"
    return "en"


# ── Embedding (Google only — free, works for Hindi + English) ──────────────────

def _embed_google(texts: List[str]) -> List[List[float]]:
    """
    Google gemini-embedding-001
    Free, 3072-dim, excellent for Hindi and English.
    """
    from google import genai
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    results = []
    for text in texts:
        result = client.models.embed_content(
            model="models/gemini-embedding-001",
            contents=text,
        )
        results.append(list(result.embeddings[0].values))
    return results


def embed_text(text: str) -> List[float]:
    """Embed single text using Google."""
    try:
        return _embed_google([text])[0]
    except Exception as e:
        print(f"[Embed] Failed: {e}")
        return [0.0] * 3072


def embed_batch(texts: List[str]) -> List[List[float]]:
    """Batch embed — falls back to one-by-one if batch fails."""
    if not texts:
        return []
    try:
        return _embed_google(texts)
    except Exception as e:
        print(f"[Embed] Batch failed: {e}, trying one by one...")
        results = []
        for text in texts:
            results.append(embed_text(text))
        return results


# ── Math helpers ───────────────────────────────────────────────────────────────

def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot   = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a ** 2 for a in vec_a))
    mag_b = math.sqrt(sum(b ** 2 for b in vec_b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return round(dot / (mag_a * mag_b), 4)


def compute_centroid(vectors: List[List[float]]) -> List[float]:
    if not vectors:
        return []
    # Filter out zero vectors (failed embeddings)
    valid = [v for v in vectors if any(x != 0 for x in v)]
    if not valid:
        return []
    n   = len(valid)
    dim = len(valid[0])
    return [round(sum(v[i] for v in valid) / n, 4) for i in range(dim)]


# ── Centroid management ────────────────────────────────────────────────────────

def build_pillar_centroids(force_rebuild: bool = False) -> Dict[str, List[float]]:
    global _centroid_cache
    if _centroid_cache and not force_rebuild:
        return _centroid_cache

    if not force_rebuild:
        try:
            from supabase_store import get_client
            db     = get_client()
            result = db.table("pillar_centroids").select("*").execute()
            if result.data and len(result.data) >= 20:
                print(f"[Classifier] Loaded {len(result.data)} centroids from Supabase")
                _centroid_cache = {r["pillar"]: r["centroid"] for r in result.data}
                return _centroid_cache
        except Exception as e:
            print(f"[Classifier] Supabase load failed: {e}, rebuilding...")

    print("[Classifier] Building pillar centroids with Google embeddings...")
    centroids = {}
    for pillar, examples in PILLAR_EXAMPLES.items():
        print(f"  Embedding {pillar} ({len(examples)} examples)...")
        try:
            vectors           = embed_batch(examples)
            centroid          = compute_centroid(vectors)
            centroids[pillar] = centroid
            dim               = len(centroid)
            print(f"  OK {pillar} → {dim}-dim centroid")
        except Exception as e:
            print(f"  FAIL {pillar}: {e}")
            centroids[pillar] = []

    try:
        from supabase_store import get_client
        db = get_client()
        for pillar, centroid in centroids.items():
            if centroid:
                db.table("pillar_centroids").upsert({
                    "pillar":     pillar,
                    "centroid":   centroid,
                    "updated_at": "now()",
                }, on_conflict="pillar").execute()
        saved = sum(1 for c in centroids.values() if c)
        print(f"[Classifier] Saved {saved}/{len(centroids)} centroids to Supabase")
    except Exception as e:
        print(f"[Classifier] Supabase save failed: {e}")

    _centroid_cache = centroids
    return centroids


def get_centroids() -> Dict[str, List[float]]:
    if not _centroid_cache:
        return build_pillar_centroids()
    return _centroid_cache


def get_api_trigger_centroids() -> Dict[str, List[float]]:
    global _api_trigger_cache
    if _api_trigger_cache:
        return _api_trigger_cache

    try:
        from supabase_store import get_client
        db     = get_client()
        result = db.table("api_trigger_centroids").select("*").execute()
        if result.data and len(result.data) >= 5:
            _api_trigger_cache = {r["trigger"]: r["centroid"] for r in result.data}
            return _api_trigger_cache
    except Exception:
        pass

    print("[Classifier] Building API trigger centroids...")
    centroids = {}
    for trigger, examples in API_TRIGGER_EXAMPLES.items():
        try:
            vectors            = embed_batch(examples)
            centroids[trigger] = compute_centroid(vectors)
            print(f"  OK {trigger}")
        except Exception as e:
            print(f"  FAIL {trigger}: {e}")

    try:
        from supabase_store import get_client
        db = get_client()
        for trigger, centroid in centroids.items():
            if centroid:
                db.table("api_trigger_centroids").upsert({
                    "trigger":    trigger,
                    "centroid":   centroid,
                    "updated_at": "now()",
                }, on_conflict="trigger").execute()
    except Exception:
        pass

    _api_trigger_cache = centroids
    return centroids


def check_api_triggers(embedding: List[float]) -> Dict[str, float]:
    triggers  = get_api_trigger_centroids()
    activated = {}
    for trigger, centroid in triggers.items():
        if not centroid:
            continue
        score     = cosine_similarity(embedding, centroid)
        threshold = API_THRESHOLDS.get(trigger, 0.70)
        if score >= threshold:
            activated[trigger] = round(score, 3)
    return dict(sorted(activated.items(), key=lambda x: x[1], reverse=True))


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class ClassifiedInput:
    text:          str
    core:          str
    emotion:       str
    functional:    str
    modifiers:     List[str]
    core_score:    float = 0.0
    keyword_count: int   = 0
    pillar_vector: List[float] = field(default_factory=list)
    pillar_scores: Dict[str, float] = field(default_factory=dict)
    embedding:     List[float] = field(default_factory=list)
    language:      str   = "en"
    timestamp:     float = field(default_factory=time.time)
    api_triggers:  Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "core":          self.core,
            "emotion":       self.emotion,
            "functional":    self.functional,
            "modifiers":     self.modifiers,
            "core_score":    self.core_score,
            "keyword_count": self.keyword_count,
            "pillar_vector": self.pillar_vector,
            "pillar_scores": self.pillar_scores,
            "language":      self.language,
            "api_triggers":  self.api_triggers,
        }


MODIFIERS_MAP = {
    "QUANTITY":    ["how many","how much","number","count","total","amount"],
    "SPECIFICITY": ["specific","exactly","particular","precise","detail"],
    "FORMAT":      ["list","table","summary","brief","detailed","explain"],
    "LOCATION":    ["where","location","place","near","city","country"],
    "EXCLUSION":   ["not","except","without","avoid","exclude","skip"],
    "URGENCY":     ["urgent","asap","now","immediately","today","quick","jaldi"],
    "CONDITION":   ["if","when","unless","only if","depends","agar"],
    "PREFERENCE":  ["prefer","like","want","favorite","best","ideal","chahiye"],
    "TEMPORAL":    ["yesterday","today","tomorrow","week","month","kal","aaj"],
    "COMPARISON":  ["vs","versus","compare","better","worse","ya","or"],
}


def _detect_modifiers(text: str) -> List[str]:
    lower = text.lower()
    return [mod for mod, kws in MODIFIERS_MAP.items()
            if any(kw in lower for kw in kws)]


# ── Main classifier ────────────────────────────────────────────────────────────

def classify_input(text: str) -> ClassifiedInput:
    """
    Full embedding-based classification.
    No keyword matching. Pure cosine similarity.
    Uses Google text-embedding-004 (free).
    """
    lang      = _detect_language(text)
    embedding = embed_text(text)
    centroids = get_centroids()

    scores = {}
    for pillar, centroid in centroids.items():
        if centroid and len(centroid) == len(embedding):
            scores[pillar] = cosine_similarity(embedding, centroid)

    if not scores:
        return ClassifiedInput(
            text=text, core="GENERAL", emotion="NEUTRAL",
            functional="CHAT", modifiers=[],
            pillar_vector=[0.0] * len(DIMENSION_ORDER),
            embedding=embedding, language=lang,
        )

    core_scores  = {p: scores.get(p, 0) for p in CORE_PILLARS}
    emo_scores   = {p: scores.get(p, 0) for p in EMOTION_PILLARS}
    func_scores  = {p: scores.get(p, 0) for p in FUNCTIONAL_PILLARS}

    core       = max(core_scores,  key=core_scores.get)
    emotion    = max(emo_scores,   key=emo_scores.get)
    functional = max(func_scores,  key=func_scores.get)

    pillar_vector = [round(scores.get(dim, 0.0), 4) for dim in DIMENSION_ORDER]
    modifiers     = _detect_modifiers(text)
    api_triggers  = check_api_triggers(embedding)
    non_zero      = {k: round(v, 4) for k, v in scores.items() if v > 0.05}

    return ClassifiedInput(
        text=text, core=core, emotion=emotion, functional=functional,
        modifiers=modifiers, core_score=core_scores[core],
        keyword_count=0, pillar_vector=pillar_vector,
        pillar_scores=non_zero, embedding=embedding,
        language=lang, api_triggers=api_triggers,
    )
