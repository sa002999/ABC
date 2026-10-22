CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE store_booking_settings (
    store_id uuid PRIMARY KEY REFERENCES stores(id),
    cleaning_minutes integer NOT NULL CHECK (cleaning_minutes BETWEEN 0 AND 1440),
    closes_at time NOT NULL,
    is_demo boolean NOT NULL DEFAULT false
);
CREATE TABLE availability_slots (
    id uuid PRIMARY KEY,
    store_id uuid NOT NULL REFERENCES stores(id),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    capacity_total integer NOT NULL CHECK (capacity_total>=0),
    status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CLOSED')),
    version integer NOT NULL DEFAULT 1,
    is_demo boolean NOT NULL DEFAULT false,
    CHECK (ends_at>starts_at),
    UNIQUE(store_id,starts_at)
);
CREATE TABLE inventory_items (
    id uuid PRIMARY KEY,
    code text NOT NULL UNIQUE,
    store_id uuid NOT NULL REFERENCES stores(id),
    kimono_id uuid NOT NULL REFERENCES kimonos(id),
    size text NOT NULL,
    status text NOT NULL DEFAULT 'AVAILABLE' CHECK (status IN ('AVAILABLE','ON_LOAN','CLEANING','MAINTENANCE','LOST','INACTIVE')),
    is_demo boolean NOT NULL DEFAULT false
);
CREATE INDEX inventory_items_selection_idx ON inventory_items(store_id,kimono_id,size,status);
CREATE TABLE booking_drafts (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id),
    data jsonb NOT NULL,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT now()+interval '7 days'
);
CREATE INDEX booking_drafts_owner_idx ON booking_drafts(user_id,updated_at DESC);
CREATE TABLE booking_quotes (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id),
    draft_id uuid NOT NULL REFERENCES booking_drafts(id),
    draft_version integer NOT NULL,
    pricing_hash text NOT NULL,
    line_items jsonb NOT NULL,
    total integer NOT NULL CHECK (total>=0),
    currency text NOT NULL DEFAULT 'TWD' CHECK (currency='TWD'),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT now()+interval '5 minutes'
);
CREATE TABLE availability_holds (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id),
    draft_id uuid NOT NULL REFERENCES booking_drafts(id),
    draft_version integer NOT NULL,
    quote_id uuid NOT NULL REFERENCES booking_quotes(id),
    store_id uuid NOT NULL REFERENCES stores(id),
    slot_id uuid NOT NULL REFERENCES availability_slots(id),
    party_size integer NOT NULL CHECK (party_size BETWEEN 1 AND 3),
    status text NOT NULL DEFAULT 'HELD' CHECK (status IN ('HELD','EXPIRED','RELEASED','PAYMENT_PENDING','RESERVED')),
    idempotency_key uuid NOT NULL,
    request_hash text NOT NULL,
    total integer NOT NULL CHECK (total>=0),
    snapshot jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT now()+interval '10 minutes',
    UNIQUE(user_id,idempotency_key)
);
CREATE INDEX availability_holds_slot_idx ON availability_holds(slot_id,status);
CREATE INDEX availability_holds_draft_idx ON availability_holds(draft_id,status);
CREATE TABLE inventory_allocations (
    id uuid PRIMARY KEY,
    inventory_id uuid NOT NULL REFERENCES inventory_items(id),
    hold_id uuid NOT NULL REFERENCES availability_holds(id),
    guest_index integer NOT NULL CHECK (guest_index BETWEEN 0 AND 2),
    rental_starts_at timestamptz NOT NULL,
    rental_ends_at timestamptz NOT NULL,
    cleaning_ends_at timestamptz NOT NULL,
    status text NOT NULL DEFAULT 'HELD' CHECK (status IN ('HELD','RESERVED','RELEASED')),
    CHECK (rental_ends_at>rental_starts_at AND cleaning_ends_at>=rental_ends_at),
    UNIQUE(hold_id,guest_index),
    EXCLUDE USING gist (inventory_id WITH =,tstzrange(rental_starts_at,cleaning_ends_at,'[)') WITH &&)
        WHERE (status IN ('HELD','RESERVED'))
);
