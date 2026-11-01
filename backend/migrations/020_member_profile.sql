ALTER TABLE users ADD COLUMN phone_number text UNIQUE,
    ADD COLUMN phone_verified_at timestamptz;

-- A successful SMS sign-in proof can bind only once, even after a later replacement.
CREATE TABLE member_phone_proofs (
    firebase_uid text NOT NULL,
    auth_time bigint NOT NULL,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    phone_number text NOT NULL,
    PRIMARY KEY (firebase_uid, auth_time)
);
