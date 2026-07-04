-- ── Migration 002: Performance Indexes ────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_stm_session_timestamp
  ON public.stm_clusters(session_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_ltm_user_strength
  ON public.ltm_patterns(user_id, strength DESC);

CREATE INDEX IF NOT EXISTS idx_messages_session_timestamp
  ON public.messages(session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sessions_user_created
  ON public.sessions(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_user_unread
  ON public.care_alerts(user_id, sent_at DESC)
  WHERE read_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_care_relationships_user_id
  ON public.care_relationships(user_id);

CREATE INDEX IF NOT EXISTS idx_care_relationships_caregiver_id
  ON public.care_relationships(caregiver_id);

CREATE INDEX IF NOT EXISTS idx_care_alerts_user_id
  ON public.care_alerts(user_id);

CREATE INDEX IF NOT EXISTS idx_care_alerts_caregiver_id
  ON public.care_alerts(caregiver_id);

CREATE INDEX IF NOT EXISTS idx_pillar_weights_user
  ON public.user_pillar_weights(user_id);
