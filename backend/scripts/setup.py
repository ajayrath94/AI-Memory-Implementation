#!/usr/bin/env python3
"""
NANCY SETUP SCRIPT
Run once on a fresh environment to set up everything.

Usage:
  cd backend
  python3 scripts/setup.py
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

REQUIRED_VARS = [
    "SUPABASE_URL", "SUPABASE_KEY", "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY", "API_KEYS", "SENDGRID_API_KEY", "SENDGRID_FROM_EMAIL",
]

def check_env():
    print("\n── Environment Variables ──────────────────────────")
    missing = []
    for var in REQUIRED_VARS:
        val = os.getenv(var)
        if val:
            print(f"  ✅ {var} = {val[:12]}...")
        else:
            print(f"  ❌ {var} = MISSING")
            missing.append(var)
    if missing:
        print(f"\n❌ Missing: {', '.join(missing)}")
        return False
    print("\n✅ All required environment variables present")
    return True

def check_supabase():
    print("\n── Supabase Connection ───────────────────────────")
    try:
        from supabase_store import get_client
        db = get_client()
        db.table("user_profile").select("user_id").limit(1).execute()
        print("  ✅ Connected")
        return True
    except Exception as e:
        print(f"  ❌ {e}")
        return False

def check_tables():
    print("\n── Database Tables ───────────────────────────────")
    tables = [
        "sessions","messages","cache_slots","stm_clusters","ltm_patterns",
        "user_memory","user_profile","pillar_centroids","caregivers",
        "care_relationships","care_alerts","user_pillar_weights"
    ]
    try:
        from supabase_store import get_client
        db = get_client()
        missing = []
        for t in tables:
            try:
                db.table(t).select("*").limit(0).execute()
                print(f"  ✅ {t}")
            except Exception:
                print(f"  ❌ {t} MISSING")
                missing.append(t)
        if missing:
            print(f"\n⚠️  Run migrations/001_initial_schema.sql in Supabase SQL editor")
        return len(missing) == 0
    except Exception as e:
        print(f"  ❌ {e}")
        return False

def check_anthropic():
    print("\n── Anthropic API ─────────────────────────────────")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        client.messages.create(model="claude-haiku-4-5", max_tokens=5,
            messages=[{"role":"user","content":"OK"}])
        print("  ✅ Connected")
        return True
    except Exception as e:
        print(f"  ❌ {e}")
        return False

def check_gemini():
    print("\n── Gemini Embeddings ─────────────────────────────")
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        r = genai.embed_content(model="models/gemini-embedding-001", content="test")
        print(f"  ✅ Connected — {len(r['embedding'])} dims")
        return True
    except Exception as e:
        print(f"  ❌ {e}")
        return False

def check_sendgrid():
    print("\n── SendGrid ──────────────────────────────────────")
    key   = os.getenv("SENDGRID_API_KEY")
    email = os.getenv("SENDGRID_FROM_EMAIL")
    if key and email:
        print(f"  ✅ From: {email}")
        return True
    print("  ❌ Missing keys")
    return False

def seed_test_data():
    print("\n── Seeding test data ─────────────────────────────")
    try:
        from supabase_store import get_client
        db = get_client()
        existing = db.table("user_profile").select("user_id").eq("user_id","test_user").execute()
        if not existing.data:
            db.table("user_profile").insert({"user_id":"test_user","name":"Test User","language_pref":"hinglish"}).execute()
            print("  ✅ Created test_user")
        else:
            print("  ✅ test_user exists")
        return True
    except Exception as e:
        print(f"  ❌ {e}")
        return False

if __name__ == "__main__":
    print("╔══════════════════════════════════════╗")
    print("║     Nancy AI — Setup & Health Check  ║")
    print("╚══════════════════════════════════════╝")

    results = {
        "env":       check_env(),
        "supabase":  check_supabase(),
        "tables":    check_tables(),
        "anthropic": check_anthropic(),
        "gemini":    check_gemini(),
        "sendgrid":  check_sendgrid(),
    }

    seed = input("\nSeed test data? (y/n): ").strip().lower()
    if seed == "y":
        results["seed"] = seed_test_data()

    print("\n── Summary ───────────────────────────────────────")
    for check, passed in results.items():
        print(f"  {'✅' if passed else '❌'} {check}")

    if all(results.values()):
        print("\n✅ Ready! Start with:")
        print("   uvicorn main:app --host 0.0.0.0 --port 8000 --reload")
    else:
        print("\n❌ Fix issues above and run again.")
        sys.exit(1)
