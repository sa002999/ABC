CREATE TABLE users (
    id uuid PRIMARY KEY,
    firebase_uid varchar(128) NOT NULL UNIQUE,
    email text NOT NULL,
    email_verified boolean NOT NULL DEFAULT false,
    display_name text,
    role text NOT NULL DEFAULT 'CUSTOMER' CHECK (role IN ('CUSTOMER', 'STORE_STAFF', 'ADMIN')),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
