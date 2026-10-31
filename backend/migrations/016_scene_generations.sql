ALTER TABLE generation_jobs DROP CONSTRAINT generation_jobs_kind_check;
ALTER TABLE generation_jobs ADD CONSTRAINT generation_jobs_kind_check CHECK (kind IN ('TRY_ON','SCENE'));
ALTER TABLE generation_jobs ADD COLUMN parent_job_id uuid REFERENCES generation_jobs(id);
ALTER TABLE generation_jobs ADD COLUMN scene_id text CHECK (scene_id IN ('CHERRY_BLOSSOM','TEMPLE'));
ALTER TABLE generation_jobs ADD COLUMN scene_prompt text;
ALTER TABLE generation_jobs ADD CONSTRAINT generation_scene_source_check CHECK (
 (kind='TRY_ON' AND parent_job_id IS NULL AND scene_id IS NULL AND scene_prompt IS NULL)
 OR (kind='SCENE' AND parent_job_id IS NOT NULL AND scene_id IS NOT NULL AND scene_prompt IS NOT NULL));
CREATE INDEX generation_jobs_scene_reuse_idx ON generation_jobs(user_id,reuse_key,created_at DESC) WHERE kind='SCENE';
