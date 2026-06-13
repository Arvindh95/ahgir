# Person Re-ID (body matching) — rollout runbook

Pairs an orthogonal **body / clothing** embedding with the existing face match
to separate biological lookalikes (siblings, parent/child) who pass the face
gate at ~0.99. Family members at one event wear different clothes, so a sibling
false-positive that clears the face floor fails the Re-ID gate.

Branch: `claude/reid-body-matching` (NOT merged to main during development —
deploy is main-only, so prod is untouched until each phase is verified and
merged). CI (Test) runs on every branch push.

## Architecture

- **reid-api** sidecar — Flask + onnxruntime (CPU), OSNet-AIN-x1.0 ONNX.
  `POST /embed` → 512-d L2-normalised vector. `GET /healthcheck`. Model file
  is mounted from `reid-api/models/` (NOT baked into the image), so a missing
  model degrades to 503 and everything fail-soft falls back to face-only.
- `faces.reid_embedding vector(512) NULL` + ivfflat cosine index.
- `backend/app/body_crop.py` — single source of truth for the face→upper-body
  crop geometry (sides 0.5×w, up 0.5×h, down 4.0×h, clipped). Index time, the
  Phase 1 backfill, and the scan probe ALL derive the crop here; a drift would
  push probe and gallery embeddings into different manifold regions and wreck
  recall.

## One-time setup — export the ONNX model

Until this is done the sidecar starts but `/embed` returns 503 (fail-soft: no
harm, embeddings stay NULL). On a host with torch:

```bash
cd reid-api
python scripts/export_onnx.py          # writes models/osnet_ain_x1_0.onnx
docker compose restart reid-api
curl -s localhost:5000/healthcheck      # {"status":"ok",...}
```

## Phases

| Phase | What | Enforced? | Action |
|------|------|-----------|--------|
| 0 | Sidecar + index-time embedding + schema | n/a | merged code |
| 1 | Backfill NULL embeddings on existing events | n/a | run job/endpoint |
| 2 | Scan computes probe Re-ID, logs gate decision | **No (shadow)** | deploy + observe |
| 3 | Enforce the gate | **Yes** | env flip + restart |

### Phase 1 — backfill

Fills `faces.reid_embedding` left NULL (legacy + fail-soft index misses).
Idempotent — only touches NULL rows; safe to re-run after the sidecar is up.

```bash
# whole instance
docker compose exec backend python -m app.workers.reid_backfill
# one event, or rate-limited incremental
docker compose exec backend python -m app.workers.reid_backfill --event <UUID> --max-images 500
```

Or per-event via the admin API (owner/superadmin), which enqueues on the
retention queue: `POST /events/{id}/reid-backfill`.

Watch progress trend to zero:

```sql
SELECT count(*) FILTER (WHERE reid_embedding IS NULL) AS still_null,
       count(*) AS total
FROM faces;
```

### Phase 2 — shadow mode (default after deploy)

`REID_ENABLED_SCAN=false`. Each scan computes the probe's body embedding from
the full video frame the frontend now sends (`full_frames`), cosine-compares
to each candidate, and writes `scan_match_metrics.reid_similarity` +
`reid_would_pass` **without enforcing**. Run for ~48h of real traffic, then
validate that Re-ID separates a known sibling pair:

```sql
SELECT image_id,
       scored_similarity AS face_sim,
       reid_similarity,
       reid_would_pass
FROM   scan_match_metrics
WHERE  reid_similarity IS NOT NULL
  AND  event_id = '<event-with-known-siblings>'
ORDER  BY created_at DESC;
```

Expect: self ≳ 0.65, sister/lookalike ≲ 0.40. If separation holds, proceed.
If `reid_similarity` is mostly NULL, the probe had no detectable body (frontend
full-frame too tight / sidecar down) — fix before Phase 3.

### Phase 3 — enable the gate (env only, no code)

Once shadow data confirms separation:

```bash
# in .env.production on the VPS
REID_ENABLED_SCAN=true

docker compose up -d backend          # or: docker compose restart backend
```

The gate drops a match ONLY when its face similarity already cleared
`REID_FACE_MIN_FOR_GATE` (0.90) AND its body cosine is below
`REID_SIMILARITY_THRESHOLD` (0.65). Candidates with NULL Re-ID (mid-backfill,
or probe had no body) bypass the gate — missing data never hides a real match.

**Rollback** (instant, no deploy): set `REID_ENABLED_SCAN=false`, restart
backend. Watch scan success rate for false-negative spikes after enabling.

## Fail-soft guarantees

- Sidecar down / model missing → `/embed` 503 → embeddings NULL, scan falls
  back to face-only. Never blocks indexing or scanning.
- `depends_on: reid-api` uses `condition: service_started` (not `_healthy`),
  so the backend/worker boot even when the sidecar is unhealthy.
- Probe detection / embed errors at scan time → gate skipped for that scan.
