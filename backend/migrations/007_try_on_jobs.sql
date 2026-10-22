CREATE TABLE generation_jobs (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id),
    session_id uuid NOT NULL REFERENCES try_on_sessions(id),
    plan_id uuid NOT NULL REFERENCES plans(id),
    kimono_id uuid NOT NULL REFERENCES kimonos(id),
    size text NOT NULL,
    photo_id uuid REFERENCES person_photos(id),
    model_id uuid REFERENCES store_models(id),
    source text NOT NULL DEFAULT 'WEBSITE' CHECK (source IN ('WEBSITE','MCP')),
    kind text NOT NULL DEFAULT 'TRY_ON' CHECK (kind='TRY_ON'),
    status text NOT NULL CHECK (status IN ('QUEUED','VALIDATING','GENERATING','SUCCEEDED','FAILED','EXPIRED','DELETED')),
    idempotency_key uuid NOT NULL,
    request_hash text NOT NULL,
    usage_day date NOT NULL,
    provider text NOT NULL DEFAULT 'GOOGLE_VERTEX_AI',
    provider_model text NOT NULL,
    provider_location text NOT NULL,
    provider_calls integer NOT NULL DEFAULT 0,
    failure_code text,
    result_key text NOT NULL,
    cleanup_pending boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    confirmed_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    expires_at timestamptz,
    deleted_at timestamptz,
    UNIQUE (user_id,idempotency_key),
    CHECK ((photo_id IS NULL) <> (model_id IS NULL))
);
CREATE INDEX generation_jobs_owner_idx ON generation_jobs(user_id,created_at DESC,id DESC);
CREATE INDEX generation_jobs_queue_idx ON generation_jobs(created_at) WHERE status='QUEUED';
CREATE TABLE generation_usage (
    user_id uuid NOT NULL REFERENCES users(id),
    source text NOT NULL CHECK (source IN ('WEBSITE','MCP')),
    day date NOT NULL,
    used integer NOT NULL DEFAULT 0 CHECK (used>=0),
    PRIMARY KEY(user_id,source,day)
);
ALTER TABLE looks ADD COLUMN generation_id uuid REFERENCES generation_jobs(id);
