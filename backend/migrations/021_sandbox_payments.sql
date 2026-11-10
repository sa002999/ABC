CREATE TABLE payment_orders (
 order_no text PRIMARY KEY,
 user_id uuid NOT NULL REFERENCES users(id),
 hold_id uuid NOT NULL UNIQUE REFERENCES availability_holds(id),
 idempotency_key uuid NOT NULL,
 quote_id uuid NOT NULL,
 total integer NOT NULL CHECK(total>0),
 currency text NOT NULL DEFAULT 'TWD' CHECK(currency='TWD'),
 merchant_id text NOT NULL,
 bank_transaction_id text NOT NULL UNIQUE,
 rec_trade_id text UNIQUE,
 status text NOT NULL DEFAULT 'PAYMENT_PENDING' CHECK(status IN ('PAYMENT_PENDING','AUTHORIZED','PAID','FAILED','REVIEW_REQUIRED','REFUND_REQUIRED')),
 policy_version text NOT NULL,
 contact jsonb NOT NULL,
 snapshot jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 checked_at timestamptz,
 UNIQUE(user_id,idempotency_key)
);
CREATE TABLE bookings (
 booking_no text PRIMARY KEY,
 order_no text NOT NULL UNIQUE REFERENCES payment_orders(order_no),
 user_id uuid NOT NULL REFERENCES users(id),
 status text NOT NULL DEFAULT 'CONFIRMED' CHECK(status='CONFIRMED'),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX payment_orders_reconcile_idx ON payment_orders(checked_at) WHERE status IN ('PAYMENT_PENDING','AUTHORIZED');
CREATE INDEX bookings_owner_idx ON bookings(user_id,created_at DESC);
