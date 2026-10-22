-- Keep the local source key for explicit rollback; publish only verified S3 objects.
ALTER TABLE product_assets ADD COLUMN s3_key text;
ALTER TABLE product_assets ADD CONSTRAINT product_assets_s3_key_format CHECK (
    s3_key IS NULL OR s3_key ~ '^catalog/[0-9a-f-]{36}/[0-9a-f]{64}\.webp$'
);
