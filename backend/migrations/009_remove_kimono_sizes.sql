-- Keep physical inventory and booking relationships while removing garment attributes.
ALTER TABLE kimonos DROP COLUMN sizes;
ALTER TABLE looks DROP COLUMN size;
ALTER TABLE try_on_sessions DROP COLUMN size;
ALTER TABLE generation_jobs DROP COLUMN size;
ALTER TABLE inventory_items DROP COLUMN size;
CREATE INDEX inventory_items_selection_idx ON inventory_items(store_id,kimono_id,status);

CREATE FUNCTION pg_temp.clean_outfit(value jsonb) RETURNS jsonb LANGUAGE plpgsql AS $$
BEGIN
    IF jsonb_typeof(value)='object' THEN
        RETURN COALESCE((SELECT jsonb_object_agg(key,pg_temp.clean_outfit(val))
            FROM jsonb_each(value) AS entry(key,val) WHERE key NOT IN ('size','sizes')), '{}'::jsonb);
    ELSIF jsonb_typeof(value)='array' THEN
        RETURN COALESCE((SELECT jsonb_agg(pg_temp.clean_outfit(val) ORDER BY ord)
            FROM jsonb_array_elements(value) WITH ORDINALITY AS entry(val,ord)), '[]'::jsonb);
    END IF;
    RETURN value;
END $$;

UPDATE booking_drafts SET data=pg_temp.clean_outfit(data);
UPDATE booking_quotes SET line_items=pg_temp.clean_outfit(line_items);
UPDATE availability_holds SET snapshot=pg_temp.clean_outfit(snapshot);

-- Merge equivalent saved outfits and retain links from unfinished bookings.
CREATE TEMP TABLE look_aliases ON COMMIT DROP AS
    SELECT id,first_value(id) OVER (PARTITION BY user_id,plan_id,kimono_id,generation_id
        ORDER BY updated_at DESC,id DESC) AS retained_id FROM looks;

UPDATE booking_drafts d SET data=jsonb_set(d.data,'{guests}',(
    SELECT jsonb_agg(CASE WHEN alias.retained_id IS NOT NULL
        THEN jsonb_set(guest,'{savedLookId}',to_jsonb(alias.retained_id::text)) ELSE guest END ORDER BY ord)
    FROM jsonb_array_elements(d.data->'guests') WITH ORDINALITY AS guests(guest,ord)
    LEFT JOIN look_aliases alias ON alias.id::text=guest->>'savedLookId'
)) WHERE jsonb_array_length(d.data->'guests')>0;

DELETE FROM looks WHERE id IN (SELECT id FROM look_aliases WHERE id<>retained_id);

-- Match LookSelection.fingerprint(): sorted Python JSON with its default spacing.
ALTER TABLE looks DROP CONSTRAINT looks_user_id_configuration_hash_key;
UPDATE looks SET configuration_hash=encode(sha256(convert_to(
    '{"accessory_ids": [], "generation_id": ' || COALESCE(to_jsonb(generation_id)::text,'null') ||
    ', "kimono_id": "' || kimono_id::text || '", "plan_id": "' || plan_id::text ||
    '", "scene_id": null}', 'UTF8')), 'hex');
UPDATE looks SET request_hash=configuration_hash;
ALTER TABLE looks ADD UNIQUE (user_id,configuration_hash);

UPDATE inventory_items SET code=regexp_replace(code,'-[SML]-001$',
    CASE substring(code FROM '-([SML])-001$') WHEN 'S' THEN '-001' WHEN 'M' THEN '-002' ELSE '-003' END)
    WHERE is_demo AND code ~ '^DEMO-.*-[SML]-001$';
UPDATE plans SET description=replace(description::text,'、尺寸','')::jsonb
    WHERE is_demo AND description::text LIKE '%、尺寸%';
