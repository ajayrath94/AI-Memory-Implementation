-- ── Migration 003: Auth Setup ─────────────────────────────────────────────────
-- Run after enabling Supabase Auth in dashboard

-- Auto-confirm emails for development (disable in production)
-- UPDATE auth.config SET value = 'false' WHERE key = 'mailer_autoconfirm';

-- Function to auto-create user_profile on phone OTP signup
CREATE OR REPLACE FUNCTION public.handle_new_user_phone()
RETURNS trigger AS $$
BEGIN
  IF NEW.phone IS NOT NULL AND NEW.email IS NULL THEN
    INSERT INTO public.user_profile (user_id, phone)
    VALUES (NEW.phone, NEW.phone)
    ON CONFLICT (user_id) DO NOTHING;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger: auto-create user_profile when phone user signs up
DROP TRIGGER IF EXISTS on_auth_user_created_phone ON auth.users;
CREATE TRIGGER on_auth_user_created_phone
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user_phone();

-- Function to auto-link caregiver auth_id on signup
CREATE OR REPLACE FUNCTION public.handle_new_caregiver()
RETURNS trigger AS $$
BEGIN
  -- Update auth_id in caregivers table when a new auth user is created
  -- This runs when caregiver verifies their email
  UPDATE public.caregivers
  SET auth_id = NEW.id
  WHERE email = NEW.email AND auth_id IS NULL;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger: auto-link caregiver auth_id
DROP TRIGGER IF EXISTS on_auth_caregiver_confirmed ON auth.users;
CREATE TRIGGER on_auth_caregiver_confirmed
  AFTER UPDATE OF email_confirmed_at ON auth.users
  FOR EACH ROW
  WHEN (OLD.email_confirmed_at IS NULL AND NEW.email_confirmed_at IS NOT NULL)
  EXECUTE FUNCTION public.handle_new_caregiver();
