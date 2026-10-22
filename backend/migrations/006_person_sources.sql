CREATE TABLE store_models (
    id uuid PRIMARY KEY,
    name jsonb NOT NULL,
    source_key text NOT NULL,
    preview_path text NOT NULL,
    warning text,
    active boolean NOT NULL DEFAULT true,
    reviewed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE try_on_sessions (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id),
    plan_id uuid NOT NULL REFERENCES plans(id),
    kimono_id uuid NOT NULL REFERENCES kimonos(id),
    size text NOT NULL,
    source text NOT NULL CHECK (source IN ('MODEL','SELF')),
    model_id uuid REFERENCES store_models(id),
    consent_version text,
    consented_at timestamptz,
    consent_revoked_at timestamptz,
    current_photo_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((source='MODEL' AND model_id IS NOT NULL) OR
           (source='SELF' AND model_id IS NULL AND consent_version IS NOT NULL AND consented_at IS NOT NULL))
);
CREATE TABLE person_photos (
    id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES try_on_sessions(id),
    user_id uuid NOT NULL REFERENCES users(id),
    raw_key text NOT NULL UNIQUE,
    source_key text,
    preview_key text,
    content_type text NOT NULL,
    expected_size integer NOT NULL CHECK (expected_size > 0 AND expected_size <= 10485760),
    status text NOT NULL CHECK (status IN ('PENDING','FILE_READY','READY','REJECTED','DELETED','EXPIRED')),
    issues jsonb NOT NULL DEFAULT '[]',
    width integer,
    height integer,
    cleanup_pending boolean NOT NULL DEFAULT false,
    raw_finalized boolean NOT NULL DEFAULT false,
    upload_expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);
ALTER TABLE try_on_sessions ADD CONSTRAINT try_on_session_photo_fk FOREIGN KEY (current_photo_id) REFERENCES person_photos(id);
CREATE INDEX person_photos_owner_idx ON person_photos(user_id,session_id);
CREATE INDEX try_on_sessions_owner_idx ON try_on_sessions(user_id,created_at DESC);
CREATE TABLE photo_audit_events (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id),
    session_id uuid NOT NULL REFERENCES try_on_sessions(id),
    photo_id uuid,
    action text NOT NULL CHECK (action IN ('CONSENT','REPLACED','DELETED','WITHDRAWN','REJECTED')),
    consent_version text,
    created_at timestamptz NOT NULL DEFAULT now()
);
