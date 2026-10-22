CREATE TABLE IF NOT EXISTS stores (
    id uuid PRIMARY KEY,
    slug text NOT NULL UNIQUE,
    city text NOT NULL CHECK (city IN ('TOKYO', 'KYOTO')),
    name jsonb NOT NULL CHECK (jsonb_typeof(name) = 'object'),
    address jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(address) = 'object'),
    latitude numeric(9,6) CHECK (latitude BETWEEN -90 AND 90),
    longitude numeric(9,6) CHECK (longitude BETWEEN -180 AND 180),
    timezone text NOT NULL DEFAULT 'Asia/Tokyo',
    opening_hours jsonb NOT NULL DEFAULT '{}'::jsonb,
    languages text[] NOT NULL DEFAULT '{}',
    active boolean NOT NULL DEFAULT true,
    is_demo boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS stores_city_active_idx ON stores (city) WHERE active;
