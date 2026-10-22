CREATE TABLE kimonos (
    id uuid PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    name jsonb NOT NULL CHECK (jsonb_typeof(name) = 'object'),
    kimono_type text NOT NULL,
    style_tags text[] NOT NULL DEFAULT '{}',
    sizes text[] NOT NULL DEFAULT '{}',
    active boolean NOT NULL DEFAULT true,
    is_demo boolean NOT NULL DEFAULT false
);
CREATE TABLE plans (
    id uuid PRIMARY KEY,
    slug text NOT NULL UNIQUE,
    kimono_id uuid NOT NULL REFERENCES kimonos(id),
    name jsonb NOT NULL CHECK (jsonb_typeof(name) = 'object'),
    summary jsonb NOT NULL CHECK (jsonb_typeof(summary) = 'object'),
    description jsonb NOT NULL CHECK (jsonb_typeof(description) = 'object'),
    audience text[] NOT NULL DEFAULT '{}',
    duration_minutes integer NOT NULL CHECK (duration_minutes > 0),
    base_price integer NOT NULL CHECK (base_price >= 0),
    currency text NOT NULL DEFAULT 'TWD' CHECK (currency = 'TWD'),
    included_items jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(included_items) = 'array'),
    active boolean NOT NULL DEFAULT true,
    is_demo boolean NOT NULL DEFAULT false
);
CREATE TABLE plan_stores (
    plan_id uuid NOT NULL REFERENCES plans(id),
    store_id uuid NOT NULL REFERENCES stores(id),
    PRIMARY KEY (plan_id, store_id)
);
CREATE TABLE product_assets (
    id uuid PRIMARY KEY,
    kimono_id uuid NOT NULL REFERENCES kimonos(id),
    kind text NOT NULL CHECK (kind IN ('PRODUCT', 'STYLED')),
    image_key text NOT NULL UNIQUE,
    alt jsonb NOT NULL CHECK (jsonb_typeof(alt) = 'object'),
    sort_order integer NOT NULL DEFAULT 0,
    active boolean NOT NULL DEFAULT true
);
CREATE INDEX plans_kimono_idx ON plans(kimono_id);
CREATE INDEX plan_stores_store_idx ON plan_stores(store_id);
CREATE INDEX product_assets_kimono_idx ON product_assets(kimono_id);
