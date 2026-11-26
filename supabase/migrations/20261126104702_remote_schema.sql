CREATE TABLE "public"."detections" (
  "id"            bigint                   GENERATED ALWAYS AS IDENTITY NOT NULL,
  "device_id"     uuid                     NOT NULL,
  "object"        text                     NOT NULL,
  "distance_m"    numeric,
  "confidence"    numeric,
  "urgency"       text                     NOT NULL,
  "lat"           double precision,
  "lng"           double precision,
  "created_at"    timestamp with time zone NOT NULL DEFAULT now(),
  "urgency_score" numeric,
  CONSTRAINT "detections_confidence_check" CHECK (((confidence >= (0)::numeric) AND (confidence <= (1)::numeric))),
  CONSTRAINT "detections_object_check" CHECK ((object = ANY (ARRAY['lubang'::text, 'orang'::text, 'motor'::text, 'mobil'::text, 'pohon'::text]))),
  CONSTRAINT "detections_pkey" PRIMARY KEY (id),
  CONSTRAINT "detections_urgency_check" CHECK ((urgency = ANY (ARRAY['Tinggi'::text, 'Sedang'::text, 'Rendah'::text])))
);

ALTER TABLE "public"."detections"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."devices" (
  "id"                 uuid                     NOT NULL DEFAULT gen_random_uuid(),
  "name"               text                     NOT NULL DEFAULT 'Vest-Care (ESP32-S3)'::text,
  "student_name"       text                     NOT NULL DEFAULT 'Nama Siswa'::text,
  "school"             text                     NOT NULL DEFAULT 'SLBN Branjangan, Jember'::text,
  "battery"            integer,
  "online"             boolean                  NOT NULL DEFAULT false,
  "last_seen"          timestamp with time zone,
  "created_at"         timestamp with time zone NOT NULL DEFAULT now(),
  "owner_id"           uuid,
  "key_hash"           text,
  "pairing_code"       text,
  "pairing_expires_at" timestamp with time zone,
  CONSTRAINT "devices_battery_check" CHECK (((battery >= 0) AND (battery <= 100))),
  CONSTRAINT "devices_pkey" PRIMARY KEY (id)
);

ALTER TABLE "public"."devices"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."gps_log" (
  "id"         bigint                   GENERATED ALWAYS AS IDENTITY NOT NULL,
  "device_id"  uuid                     NOT NULL,
  "lat"        double precision         NOT NULL,
  "lng"        double precision         NOT NULL,
  "accuracy"   real,
  "created_at" timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT "gps_log_pkey" PRIMARY KEY (id)
);

ALTER TABLE "public"."gps_log"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."profiles" (
  "id"            uuid                     NOT NULL DEFAULT gen_random_uuid(),
  "username"      text                     NOT NULL,
  "password_hash" text,
  "full_name"     text,
  "email"         text,
  "created_at"    timestamp with time zone DEFAULT now(),
  CONSTRAINT "profiles_email_key" UNIQUE (email),
  CONSTRAINT "profiles_pkey" PRIMARY KEY (id),
  CONSTRAINT "profiles_username_key" UNIQUE (username)
);

ALTER TABLE "public"."profiles"
  ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."detections"
  ADD CONSTRAINT "detections_device_id_fkey" FOREIGN KEY (device_id) REFERENCES public.devices(id) ON DELETE CASCADE;

ALTER TABLE "public"."gps_log"
  ADD CONSTRAINT "gps_log_device_id_fkey" FOREIGN KEY (device_id) REFERENCES public.devices(id) ON DELETE CASCADE;

ALTER TABLE "public"."devices"
  ADD CONSTRAINT "devices_owner_id_fkey" FOREIGN KEY (owner_id) REFERENCES public.profiles(id) ON DELETE CASCADE;

CREATE INDEX detections_created_idx ON public.detections USING btree (created_at DESC);

CREATE INDEX gps_log_created_idx ON public.gps_log USING btree (created_at DESC);

CREATE POLICY "lihat deteksi rompi sendiri" ON "public"."detections"
  FOR SELECT
  TO "authenticated"
  USING ((device_id IN ( SELECT devices.id
   FROM public.devices
  WHERE (devices.owner_id = auth.uid()))));

CREATE POLICY "lihat rompi sendiri" ON "public"."devices"
  FOR SELECT
  TO "authenticated"
  USING ((owner_id = auth.uid()));

CREATE POLICY "lihat gps rompi sendiri" ON "public"."gps_log"
  FOR SELECT
  TO "authenticated"
  USING ((device_id IN ( SELECT devices.id
   FROM public.devices
  WHERE (devices.owner_id = auth.uid()))));

ALTER PUBLICATION "supabase_realtime" ADD TABLE "public"."detections";

ALTER PUBLICATION "supabase_realtime" ADD TABLE "public"."devices";

ALTER PUBLICATION "supabase_realtime" ADD TABLE "public"."gps_log";

REVOKE ALL ON SEQUENCE "public"."detections_id_seq" FROM "anon";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."detections_id_seq" TO "anon";

REVOKE ALL ON SEQUENCE "public"."detections_id_seq" FROM "authenticated";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."detections_id_seq" TO "authenticated";

REVOKE ALL ON SEQUENCE "public"."detections_id_seq" FROM "postgres";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."detections_id_seq" TO "postgres";

REVOKE ALL ON SEQUENCE "public"."detections_id_seq" FROM "service_role";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."detections_id_seq" TO "service_role";

REVOKE ALL ON SEQUENCE "public"."gps_log_id_seq" FROM "anon";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."gps_log_id_seq" TO "anon";

REVOKE ALL ON SEQUENCE "public"."gps_log_id_seq" FROM "authenticated";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."gps_log_id_seq" TO "authenticated";

REVOKE ALL ON SEQUENCE "public"."gps_log_id_seq" FROM "postgres";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."gps_log_id_seq" TO "postgres";

REVOKE ALL ON SEQUENCE "public"."gps_log_id_seq" FROM "service_role";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."gps_log_id_seq" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."detections" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."detections" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."detections" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."detections" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."devices" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."devices" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."devices" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."devices" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."gps_log" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."gps_log" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."gps_log" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."gps_log" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."profiles" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."profiles" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."profiles" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."profiles" TO "service_role";

