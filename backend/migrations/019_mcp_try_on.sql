CREATE TABLE mcp_try_on_reviews (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id uuid NOT NULL,
    session_id uuid NOT NULL REFERENCES try_on_sessions(id),
    selection jsonb NOT NULL,
    material_version text NOT NULL,
    usage_day date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT now()+interval '10 minutes',
    job_id uuid REFERENCES generation_jobs(id)
);
CREATE INDEX mcp_try_on_reviews_owner ON mcp_try_on_reviews(user_id,conversation_id,created_at DESC);
