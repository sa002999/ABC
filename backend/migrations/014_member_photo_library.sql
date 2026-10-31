ALTER TABLE store_models ADD COLUMN role text NOT NULL DEFAULT 'FEMALE'
    CHECK (role IN ('FEMALE','MALE'));
ALTER TABLE person_photos ADD COLUMN replaces_photo_id uuid REFERENCES person_photos(id);
CREATE INDEX person_photos_library_idx ON person_photos(user_id,status);

-- Keep the latest three usable originals per member. Existing results and looks stay intact.
WITH ranked AS (
    SELECT p.id,row_number() OVER (PARTITION BY p.user_id ORDER BY p.created_at DESC,p.id DESC) AS position
    FROM person_photos p JOIN try_on_sessions s ON s.id=p.session_id AND s.user_id=p.user_id
    WHERE p.status IN ('FILE_READY','READY') AND s.source='SELF' AND s.current_photo_id=p.id
      AND s.consent_version='photo-consent-2026-10-17' AND s.consent_revoked_at IS NULL
), kept AS (SELECT id FROM ranked WHERE position<=3)
UPDATE person_photos SET status='DELETED',deleted_at=COALESCE(deleted_at,now()),cleanup_pending=true
WHERE status IN ('FILE_READY','READY') AND id NOT IN (SELECT id FROM kept);
UPDATE person_photos SET status='EXPIRED',cleanup_pending=true WHERE status='PENDING';
UPDATE try_on_sessions SET current_photo_id=NULL WHERE current_photo_id IN (
    SELECT id FROM person_photos WHERE status IN ('DELETED','EXPIRED','REJECTED'));
