ALTER TABLE generation_jobs ADD COLUMN belt_id uuid REFERENCES accessories(id);
ALTER TABLE generation_jobs ADD COLUMN outfit_key text;
ALTER TABLE generation_jobs ADD COLUMN outfit_sha256 text;
ALTER TABLE generation_jobs ADD COLUMN person_source_key text;
ALTER TABLE generation_jobs ADD COLUMN reuse_key text;
CREATE INDEX generation_jobs_reuse_idx ON generation_jobs(user_id,reuse_key,created_at DESC)
    WHERE source='WEBSITE' AND kind='TRY_ON';
