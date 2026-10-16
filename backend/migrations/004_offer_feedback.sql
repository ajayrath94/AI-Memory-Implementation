-- Offer feedback (16 Oct 2026). Run once in Supabase → SQL editor.
-- Safe to run again: every column is added only if missing.
--
-- The offer log's columns (offer_log.py) were written by the code but never
-- created, so every offer was saved without its kind, date, link or
-- festival, and the picker's history had nothing to read. They are here too.

alter table suggestions add column if not exists kind          text;
alter table suggestions add column if not exists local_date    date;
alter table suggestions add column if not exists weekday       text;
alter table suggestions add column if not exists why_now       text;
alter table suggestions add column if not exists link          text;
alter table suggestions add column if not exists festival      text;
alter table suggestions add column if not exists reply_text    text;

-- How it was offered, and what her answer said about it.
alter table suggestions add column if not exists way           text;   -- khana: outside | home
alter table suggestions add column if not exists way_she_wants text;   -- what she said she would rather
alter table suggestions add column if not exists never         boolean;
alter table suggestions add column if not exists condition     jsonb;  -- {"weekday": "Tue"} / {"fast_day": true}

create index if not exists suggestions_user_kind on suggestions (user_id, kind);

-- Make the new columns visible to the API straight away.
notify pgrst, 'reload schema';
