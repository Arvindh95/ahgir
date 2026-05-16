# Face Accuracy Branch Notes

Branch: `accuracy/multi-frame-matching`

This branch adds accuracy-focused improvements for guest face scanning and photo matching. The goal is to improve match reliability without using gender or other demographic filtering.

## Summary

The branch implements support for:

1. Multi-frame aggregation
2. Adaptive thresholds by indexed face size
3. Face quality-aware scoring
4. Candidate gap filtering for ambiguous results
5. Cluster-aware scoring support

The enhanced scan path is registered before the legacy guest router, so `POST /scan` should use the new scoring route on this branch.

## Files Added or Changed

### `backend/app/face_match_scoring.py`

Adds the core scoring logic used to rank scan results.

Main behavior:

- Groups candidate matches by image.
- Rewards photos that match across multiple scan frames.
- Applies different thresholds for large, medium, and small indexed faces.
- Adjusts required similarity based on face quality.
- Penalizes ambiguous one-frame matches when the top candidate and next candidate are too close.
- Adds optional cluster-based boosting when multiple results belong to the same face cluster.

This module does not use gender or demographic attributes.

### `backend/app/routers/guest_accuracy.py`

Adds an enhanced `POST /scan` route.

It reuses existing guest scan infrastructure where possible:

- event-token authentication
- rate limiting
- frame decoding and sanitization
- CompreFace recognition calls
- guest-safe photo URL generation
- audit logging

The difference is the final matching stage. Instead of using only the highest raw similarity per image, it calls `aggregate_face_matches()` from `face_match_scoring.py`.

### `backend/app/main.py`

Registers the new `guest_accuracy` router before the existing `guest` router.

This matters because both routers define `POST /scan`. FastAPI resolves routes in registration order, so the enhanced route must be registered first.

### `backend/app/face_quality.py`

Adds helper functions for technical face quality scoring.

Current signals:

- face minimum side in pixels
- blur/sharpness estimate
- brightness estimate
- whether the padded crop touches the image edge

These are technical image-quality signals only. They do not infer identity, gender, age, ethnicity, or any demographic attribute.

### `backend/app/face_clustering.py`

Adds helper functions for assigning deterministic face-cluster IDs from high-confidence same-person edges.

Important limitation:

- The current database stores placeholder embeddings because CompreFace owns the real embeddings internally.
- Therefore, this branch adds cluster support and helpers, but a separate background process is still needed to create high-confidence same-person edges and write `face_cluster_id` values.

### `backend/migrations/20260516_face_accuracy_fields.sql`

Adds optional face metadata columns:

```sql
face_min_side_px
blur_score
brightness_score
crop_clipped
face_cluster_id
```

Also adds indexes for cluster and quality lookups.

The migration uses `IF NOT EXISTS` so it is safe to run more than once on PostgreSQL.

### `backend/tests/test_face_match_scoring.py`

Adds tests for the scoring helper.

Covered behavior:

- thresholds vary by face size
- repeated-frame evidence can outrank single-frame evidence
- small faces require a stricter threshold
- low-quality faces require stronger similarity
- cluster evidence boosts related images

## What Is Active in Runtime

The enhanced `POST /scan` route is active on this branch because `guest_accuracy.router` is included before `guest.router` in `main.py`.

Runtime scan improvements that should be active:

- multi-frame aggregation
- adaptive thresholds
- quality-aware threshold adjustment when quality metadata exists
- candidate gap filtering
- cluster-aware boosting when `face_cluster_id` exists

## What Requires Deployment or Follow-up

### 1. Run the SQL migration

Before expecting quality and cluster metadata to be available in production/staging, run:

```bash
psql "$DATABASE_URL" -f backend/migrations/20260516_face_accuracy_fields.sql
```

The enhanced scan route has a fallback path if the migration columns are not present, but quality and cluster scoring will be limited without those fields.

### 2. Populate quality metadata during indexing

The helper for calculating quality metrics exists in `face_quality.py`, but the existing indexer still needs to be updated to persist these values into the new face columns for every indexed face.

Until that is done, quality scoring mostly falls back to the existing `quality_score` field.

### 3. Populate face clusters

Cluster-aware scoring is implemented, but it depends on `face_cluster_id` being populated.

A future background job should:

1. compare high-confidence same-person face evidence within the same event;
2. assign deterministic cluster IDs using `face_clustering.py`;
3. write `face_cluster_id` back to the `faces` table.

## Recommended Validation Steps

Run targeted tests:

```bash
cd backend
pytest tests/test_face_match_scoring.py
```

Then run the broader backend test suite:

```bash
cd backend
pytest
```

Manual validation flow:

1. Apply the migration.
2. Start the backend from this branch.
3. Upload event photos.
4. Confirm indexing still completes.
5. Scan using three different poses.
6. Compare result ordering against `main` using the same uploaded photo set.

## Notes

This branch intentionally avoids gender filtering. The accuracy improvements are based on stronger non-demographic evidence:

- multiple scan frames
- face size
- technical image quality
- score separation
- same-person cluster consistency
