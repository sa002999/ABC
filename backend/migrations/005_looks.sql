CREATE TABLE looks (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id),
    plan_id uuid NOT NULL REFERENCES plans(id),
    kimono_id uuid NOT NULL REFERENCES kimonos(id),
    size text NOT NULL,
    configuration_hash text NOT NULL,
    idempotency_key uuid,
    request_hash text NOT NULL,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, configuration_hash),
    UNIQUE (user_id, idempotency_key)
);
CREATE INDEX looks_owner_created_idx ON looks(user_id, created_at DESC, id DESC);
