-- ── Migration 001: Initial Schema ─────────────────────────────────────────────
-- Run this first on any new Supabase instance
-- Idempotent — safe to run multiple times

-- Sessions
CREATE TABLE IF NOT EXISTS public.sessions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         text NOT NULL,
  model           text,
  pillar_centroid jsonb DEFAULT '{}',
  created_at      timestamp with time zone DEFAULT now()
);

-- Messages
CREATE TABLE IF NOT EXISTS public.messages (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id  uuid REFERENCES public.sessions(id) ON DELETE CASCADE,
  role        text NOT NULL,
  content     text,
  pillar_core text,
  embedding   vector(3072),
  created_at  timestamp with time zone DEFAULT now()
);

-- Cache slots
CREATE TABLE IF NOT EXISTS public.cache_slots (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid REFERENCES public.sessions(id) ON DELETE CASCADE,
  slot_name  text NOT NULL,
  value      text,
  strength   float DEFAULT 1.0,
  created_at timestamp with time zone DEFAULT now(),
  UNIQUE(session_id, slot_name)
);

-- STM clusters
CREATE TABLE IF NOT EXISTS public.stm_clusters (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id   uuid REFERENCES public.sessions(id) ON DELETE CASCADE,
  pillar       text,
  text         text,
  strength     float DEFAULT 1.0,
  recall_count int DEFAULT 0,
  timestamp    timestamp with time zone DEFAULT now()
);

-- LTM patterns
CREATE TABLE IF NOT EXISTS public.ltm_patterns (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       text NOT NULL,
  pattern_name  text,
  text          text,
  strength      float DEFAULT 1.0,
  recall_count  int DEFAULT 0,
  fused_pillars jsonb DEFAULT '[]',
  overlap_score float DEFAULT 0,
  timestamp     timestamp with time zone DEFAULT now()
);

-- User memory
CREATE TABLE IF NOT EXISTS public.user_memory (
  user_id                  text PRIMARY KEY,
  summary                  text,
  key_facts                jsonb DEFAULT '[]',
  dominant_pillars         jsonb DEFAULT '[]',
  session_count            int DEFAULT 0,
  pillar_trend             jsonb DEFAULT '{}',
  behavioural_fingerprint  jsonb DEFAULT '{}',
  personal_centroids       jsonb DEFAULT '{}',
  session_centroids        jsonb DEFAULT '{}',
  created_at               timestamp with time zone DEFAULT now(),
  updated_at               timestamp with time zone DEFAULT now()
);

-- Pillar centroids
CREATE TABLE IF NOT EXISTS public.pillar_centroids (
  pillar     text PRIMARY KEY,
  centroid   vector(3072),
  updated_at timestamp with time zone DEFAULT now()
);

-- API trigger centroids
CREATE TABLE IF NOT EXISTS public.api_trigger_centroids (
  trigger    text PRIMARY KEY,
  centroid   vector(3072),
  updated_at timestamp with time zone DEFAULT now()
);

-- User profile
CREATE TABLE IF NOT EXISTS public.user_profile (
  user_id              text PRIMARY KEY,
  name                 text,
  age_group            text,
  location             text,
  language_pref        text DEFAULT 'hinglish',
  phone                text UNIQUE,
  family               jsonb DEFAULT '{}',
  health               jsonb DEFAULT '{}',
  interests            jsonb DEFAULT '{}',
  personality          jsonb DEFAULT '{}',
  life_context         jsonb DEFAULT '{}',
  communication        jsonb DEFAULT '{}',
  caregiver_notified_at timestamp with time zone,
  personal_centroids   jsonb DEFAULT '{}',
  created_at           timestamp with time zone DEFAULT now(),
  updated_at           timestamp with time zone DEFAULT now()
);

-- Caregivers
CREATE TABLE IF NOT EXISTS public.caregivers (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text,
  email      text UNIQUE,
  phone      text,
  org_name   text,
  org_type   text DEFAULT 'family',
  auth_id    uuid UNIQUE,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now()
);

-- Care relationships (many-to-many)
CREATE TABLE IF NOT EXISTS public.care_relationships (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  caregiver_id     uuid REFERENCES public.caregivers(id) ON DELETE CASCADE,
  user_id          text REFERENCES public.user_profile(user_id) ON DELETE CASCADE,
  relationship     text,
  alert_email      text,
  alert_phone      text,
  notify_stress    boolean DEFAULT true,
  notify_health    boolean DEFAULT true,
  notify_sadness   boolean DEFAULT true,
  notify_emergency boolean DEFAULT true,
  active           boolean DEFAULT true,
  created_at       timestamp with time zone DEFAULT now(),
  UNIQUE(caregiver_id, user_id)
);

-- Care alerts
CREATE TABLE IF NOT EXISTS public.care_alerts (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      text,
  caregiver_id uuid REFERENCES public.caregivers(id),
  alert_type   text,
  severity     text DEFAULT 'medium',
  message      text,
  pillar       text,
  session_id   uuid,
  sent_via     text,
  sent_at      timestamp with time zone DEFAULT now(),
  read_at      timestamp with time zone
);

-- User pillar weights
CREATE TABLE IF NOT EXISTS public.user_pillar_weights (
  user_id    text REFERENCES public.user_profile(user_id) ON DELETE CASCADE,
  pillar     text NOT NULL,
  weight     float DEFAULT 1.0 CHECK (weight >= 0.1 AND weight <= 2.0),
  updated_at timestamp with time zone DEFAULT now(),
  PRIMARY KEY (user_id, pillar)
);

-- Demographics and cultural context (added later)
ALTER TABLE public.user_profile ADD COLUMN IF NOT EXISTS demographics jsonb DEFAULT '{}';
ALTER TABLE public.user_profile ADD COLUMN IF NOT EXISTS cultural_context jsonb DEFAULT '{}';
