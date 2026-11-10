CREATE TABLE booking_contact_verifications (
    draft_id uuid NOT NULL REFERENCES booking_drafts(id) ON DELETE CASCADE,
    channel text NOT NULL CHECK (channel IN ('email', 'phone')),
    value text NOT NULL,
    code_hash text,
    expires_at timestamptz,
    sent_at timestamptz,
    attempts integer NOT NULL DEFAULT 0,
    verified_at timestamptz,
    PRIMARY KEY (draft_id, channel, value)
);

CREATE TABLE booking_contact_phone_proofs (
    firebase_uid text NOT NULL,
    auth_time bigint NOT NULL,
    draft_id uuid NOT NULL REFERENCES booking_drafts(id) ON DELETE CASCADE,
    PRIMARY KEY (firebase_uid, auth_time)
);
