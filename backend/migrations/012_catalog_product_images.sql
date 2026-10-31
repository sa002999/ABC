-- A rental package can offer several garments without creating extra priced plans.
CREATE TABLE plan_kimonos (
    plan_id uuid NOT NULL REFERENCES plans(id),
    kimono_id uuid NOT NULL REFERENCES kimonos(id),
    PRIMARY KEY (plan_id, kimono_id)
);
CREATE INDEX plan_kimonos_kimono_idx ON plan_kimonos(kimono_id);
INSERT INTO plan_kimonos(plan_id, kimono_id) SELECT id, kimono_id FROM plans;

ALTER TABLE accessories ADD COLUMN sku text UNIQUE;
ALTER TABLE product_assets ALTER COLUMN kimono_id DROP NOT NULL;
ALTER TABLE product_assets ADD COLUMN accessory_id uuid REFERENCES accessories(id);
ALTER TABLE product_assets ADD CONSTRAINT product_assets_one_product
    CHECK (num_nonnulls(kimono_id, accessory_id) = 1);
CREATE INDEX product_assets_accessory_idx ON product_assets(accessory_id);

UPDATE kimonos SET gender='FEMALE' WHERE sku='RKH0103';
