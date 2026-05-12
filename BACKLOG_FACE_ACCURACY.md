# Face Recognition Accuracy — Backlog

Levers to improve recall (% of a guest's photos surfaced) and precision
(no strangers in results), ordered by effort. Defer until real-user
signal says which problem actually exists.

## Current State (prod defaults, 2026-05-12)

| Setting | Value | Where |
|---|---|---|
| `face_similarity_threshold` | **0.80** | `config.py`, `docker-compose.yml` |
| Detection probability threshold | 0.3 for indexing; scan retries at 0.3 when 0.5 finds nothing | `face_indexer_compreface.py`, `guest.py` |
| `prediction_count` (scan-side top-K) | 500 | `guest.py:37` |
| Indexing quality gate: min detection prob | 0.3 | `config.py:face_min_detection_probability` |
| Indexing quality gate: min crop pixels | 32 | `config.py:face_min_crop_pixels` |
| Multi-frame scan | 3 frames, **pose-gated** (yaw-detected) | `scan.tsx` |
| Engine | CompreFace 1.2.0 (ArcFace under hood) | `docker-compose.yml` |
| API replicas | 2× `compreface-api` in prod | `docker-compose.prod.yml` |
| Subject model | One CompreFace subject per face crop (not clustered) | `face_indexer_compreface.py:255` |

## Levers, Ranked by Cost/Benefit

### Cheap (≤30 min)

| # | Lever | Effort | Recall impact | Risk |
|---|---|---|---|---|
| 1 | Add scan telemetry for score distributions and false-positive reports | 30 min | Lets thresholds be calibrated from real events instead of guesswork | Low |
| 2 | Bump capture JPEG quality 0.9 → 0.95 in `scan.tsx:263` | 5 min | +3-5% on small faces | Larger upload payload (already capped at 8MB/frame) |
| 3 | Default detection threshold 0.5 → 0.3 in `face_indexer_compreface.py` | Done | More face crops indexed | Junk faces if downstream add-face gate doesn't catch them |
| 4 | Increase scan frames 3 → 5 (add look-up + look-down phases to pose-gated flow) | 30 min | +5-10% on hard angles, especially candid downward shots | Scan UX 5s vs 3.5s |

### Medium (1-4 hrs)

| # | Lever | Effort | Recall impact | Risk |
|---|---|---|---|---|
| 5 | Add UI quality hints ("face fully visible", "remove sunglasses", "good lighting") | 1 hr | +5% by improving guest input | None |
| 6 | Client-side blur detection — reject blurry frames before upload | 4 hr | Cleaner data → better matches | Some users with low-end cameras may fail every frame |

### Expensive (1+ weeks)

| # | Lever | Effort | Recall impact | Risk |
|---|---|---|---|---|
| 7 | **Subject clustering** — cluster face crops belonging to the same person across photos. Recognition compares against averaged embedding instead of individual crops | 1 week | **+15-25%** | Big build. Reindex existing events. Embedding portability concern (#9) |
| 8 | Per-event tunable threshold (loose for casual, strict for formal) | 2 days | Per-event flexibility | UI complexity |
| 9 | Extract embeddings via CompreFace `/embedding` endpoint, store in pgvector. Reduces engine lock-in | 3-4 days | Enables future engine swap (#10) | Migration of existing events |
| 10 | Swap CompreFace → InsightFace via ONNX directly | 2-3 weeks | +5-10% (newer model) on hard cases (children, dark skin tones, occlusion) | Lose CompreFace admin UI, full reindex |

## Triggers (when to actually do these)

Don't tune blind. Watch for these signals:

| Signal | Probable lever |
|---|---|
| Guests in real events report "I'm in 50 photos but only see 30" (≥30% recall miss) | Check indexing status, reindex, then consider #7 subject clustering |
| Guests report seeing strangers' photos | Keep threshold ≥ 0.90, investigate quality gate (#3 may be too aggressive) |
| Scan times >5s on mobile network | Reduce frames or compress capture (don't do #2/#4) |
| "Why isn't my child showing up" | #5 UI hints or #10 InsightFace |
| Scan latency >10s with 1000+ photo events | Cap `prediction_count` lower, scale CompreFace API replicas |
| Photographers ask "show all photos of bride" | #7 subject clustering (this is the only path) |
| Children's faces consistently missed | #10 InsightFace (ArcFace bias on minors) |

## What's Already Shipped (don't redo)

- Threshold lowered to 0.80 for recall after missing-photo reports (2026-05-12)
- Quality gate relaxed to min_prob 0.3 and min_crop 32px (2026-05-12)
- Multi-frame scan upgraded from timer-based to **pose-gated** capture using face-api 68-point landmarks — captures straight, left, and right frames
- Retention now deletes CompreFace subjects (no orphan accumulation)

## Recommended Sequence

1. **Ship pose-gated scan** ✓ done
2. **Reindex existing events** so relaxed indexing can register previously skipped faces
3. Run a real event sample and inspect false positives vs missed photos
4. If recall is still weak, prioritize subject clustering over further threshold drops
