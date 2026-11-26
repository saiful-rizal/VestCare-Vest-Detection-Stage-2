ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS auth_user_id uuid;

CREATE UNIQUE INDEX IF NOT EXISTS profiles_auth_user_id_key
  ON public.profiles (auth_user_id);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'profiles_auth_user_id_fkey'
      AND conrelid = 'public.profiles'::regclass
  ) THEN
    ALTER TABLE public.profiles
      ADD CONSTRAINT profiles_auth_user_id_fkey
      FOREIGN KEY (auth_user_id)
      REFERENCES auth.users (id)
      ON DELETE CASCADE;
  END IF;
END;
$$;

UPDATE public.profiles AS profile
SET auth_user_id = auth_user.id,
    full_name = COALESCE(
      profile.full_name,
      NULLIF(auth_user.raw_user_meta_data ->> 'full_name', ''),
      NULLIF(auth_user.raw_user_meta_data ->> 'name', '')
    ),
    email = COALESCE(profile.email, auth_user.email)
FROM auth.users AS auth_user
WHERE profile.auth_user_id IS NULL
  AND profile.id = auth_user.id;

UPDATE public.profiles AS profile
SET auth_user_id = auth_user.id,
    full_name = COALESCE(
      profile.full_name,
      NULLIF(auth_user.raw_user_meta_data ->> 'full_name', ''),
      NULLIF(auth_user.raw_user_meta_data ->> 'name', '')
    ),
    email = COALESCE(profile.email, auth_user.email)
FROM auth.users AS auth_user
WHERE profile.auth_user_id IS NULL
  AND auth_user.email IS NOT NULL
  AND profile.email = auth_user.email;

CREATE OR REPLACE FUNCTION public.sync_profile_for_auth_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
  profile_id uuid;
  auth_full_name text;
BEGIN
  auth_full_name := COALESCE(
    NULLIF(NEW.raw_user_meta_data ->> 'full_name', ''),
    NULLIF(NEW.raw_user_meta_data ->> 'name', '')
  );

  UPDATE public.profiles
  SET auth_user_id = NEW.id,
      full_name = COALESCE(auth_full_name, full_name),
      email = COALESCE(NEW.email, email)
  WHERE email = NEW.email
    AND auth_user_id IS NULL
  RETURNING id INTO profile_id;

  IF profile_id IS NULL THEN
    INSERT INTO public.profiles (auth_user_id, username, full_name, email)
    VALUES (
      NEW.id,
      'user_' || replace(NEW.id::text, '-', ''),
      auth_full_name,
      NEW.email
    )
    ON CONFLICT (auth_user_id) DO UPDATE
    SET email = COALESCE(EXCLUDED.email, public.profiles.email),
        full_name = COALESCE(EXCLUDED.full_name, public.profiles.full_name);
  END IF;

  RETURN NEW;
END;
$function$;

INSERT INTO public.profiles (auth_user_id, username, full_name, email)
SELECT
  auth_user.id,
  'user_' || replace(auth_user.id::text, '-', ''),
  COALESCE(
    NULLIF(auth_user.raw_user_meta_data ->> 'full_name', ''),
    NULLIF(auth_user.raw_user_meta_data ->> 'name', '')
  ),
  auth_user.email
FROM auth.users AS auth_user
WHERE NOT EXISTS (
  SELECT 1
  FROM public.profiles AS profile
  WHERE profile.auth_user_id = auth_user.id
     OR (auth_user.email IS NOT NULL AND profile.email = auth_user.email)
)
ON CONFLICT (auth_user_id) DO NOTHING;

DROP TRIGGER IF EXISTS sync_profile_after_auth_insert ON auth.users;
CREATE TRIGGER sync_profile_after_auth_insert
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.sync_profile_for_auth_user();

REVOKE ALL ON FUNCTION public.sync_profile_for_auth_user() FROM PUBLIC, anon, authenticated;

DROP POLICY IF EXISTS profiles_select_own_auth_user ON public.profiles;
CREATE POLICY profiles_select_own_auth_user
  ON public.profiles
  FOR SELECT
  TO authenticated
  USING (auth_user_id = (SELECT auth.uid()));

DROP POLICY IF EXISTS profiles_update_own_auth_user ON public.profiles;
CREATE POLICY profiles_update_own_auth_user
  ON public.profiles
  FOR UPDATE
  TO authenticated
  USING (auth_user_id = (SELECT auth.uid()))
  WITH CHECK (auth_user_id = (SELECT auth.uid()));

REVOKE ALL ON TABLE public.profiles FROM anon, authenticated;
GRANT SELECT (id, username, full_name, email, created_at)
  ON TABLE public.profiles TO authenticated;
GRANT UPDATE (username, full_name)
  ON TABLE public.profiles TO authenticated;

DROP POLICY IF EXISTS "lihat rompi sendiri" ON public.devices;
CREATE POLICY "lihat rompi sendiri"
  ON public.devices
  FOR SELECT
  TO authenticated
  USING (
    owner_id IN (
      SELECT profile.id
      FROM public.profiles AS profile
      WHERE profile.auth_user_id = (SELECT auth.uid())
    )
  );

DROP POLICY IF EXISTS "lihat deteksi rompi sendiri" ON public.detections;
CREATE POLICY "lihat deteksi rompi sendiri"
  ON public.detections
  FOR SELECT
  TO authenticated
  USING (
    device_id IN (
      SELECT device.id
      FROM public.devices AS device
      WHERE device.owner_id IN (
        SELECT profile.id
        FROM public.profiles AS profile
        WHERE profile.auth_user_id = (SELECT auth.uid())
      )
    )
  );

DROP POLICY IF EXISTS "lihat gps rompi sendiri" ON public.gps_log;
CREATE POLICY "lihat gps rompi sendiri"
  ON public.gps_log
  FOR SELECT
  TO authenticated
  USING (
    device_id IN (
      SELECT device.id
      FROM public.devices AS device
      WHERE device.owner_id IN (
        SELECT profile.id
        FROM public.profiles AS profile
        WHERE profile.auth_user_id = (SELECT auth.uid())
      )
    )
  );
