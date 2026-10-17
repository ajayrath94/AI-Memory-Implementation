-- Routines per place (17 Oct 2026). Run once in Supabase -> SQL editor.
-- Safe to run again.
--
-- user_patterns keeps one row per kind (wake, sleep, active window) as
-- before; every reader is unchanged. The row now also says which place its
-- observed time is for, and keeps every place's own routine beside it.

alter table user_patterns add column if not exists place    text;
alter table user_patterns add column if not exists by_place jsonb;

notify pgrst, 'reload schema';
