-- Face accuracy metadata for live-event matching.
-- Safe to run more than once on PostgreSQL.

ALTER TABLE faces
    ADD COLUMN IF NOT EXISTS face_min_side_px FLOAT,
    ADD COLUMN IF NOT EXISTS blur_score FLOAT,
    ADD COLUMN IF NOT EXISTS brightness_score FLOAT,
    ADD COLUMN IF NOT EXISTS crop_clipped BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS face_cluster_id UUID;

CREATE INDEX IF NOT EXISTS idx_faces_event_cluster
    ON faces (event_id, face_cluster_id)
    WHERE face_cluster_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_faces_quality_cluster
    ON faces (event_id, quality_score, face_min_side_px);
