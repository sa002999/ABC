ALTER TABLE kimonos ADD COLUMN gender text NOT NULL DEFAULT 'FEMALE' CHECK (gender IN ('FEMALE','MALE'));
ALTER TABLE plans ADD COLUMN kind text NOT NULL DEFAULT 'SINGLE' CHECK (kind IN ('SINGLE','COUPLE'));
ALTER TABLE plans ADD COLUMN additional_guest_price integer NOT NULL DEFAULT 1500 CHECK (additional_guest_price >= 0);
CREATE TABLE accessories (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    category text NOT NULL CHECK (category='BELT'),
    price integer NOT NULL CHECK (price>=0),
    active boolean NOT NULL DEFAULT true
);
ALTER TABLE looks ADD COLUMN participants jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(participants)='array');
INSERT INTO accessories(id,name,category,price) VALUES
 ('20000000-0000-4000-8000-000000000001','素色腰帶','BELT',200),
 ('20000000-0000-4000-8000-000000000002','花紋腰帶','BELT',350);
