# PicUr Capacity Planning

Generated from a real conversation about scale limits. Numbers below
are honest estimates based on the current architecture (CompreFace +
Postgres + MinIO + Redis + FastAPI + Next.js, single Contabo VPS).

## Current pricing tiers vs capacity

The Free 25 / Starter 250 / Pro 500 / Custom 500+ photo caps are
**wildly inside** what one VPS can serve. The ceiling is the photo
count, not what the hardware can do — there's 5–10× headroom on every
resource at the Pro cap.

## Single-event capacity (current single VPS, 8 vCPU / 24 GB / 193 GB)

| Photos | Concurrent guests | Status |
|--------|-------------------|--------|
| 25 (Free) | 50 | Instant. No-op. |
| 250 (Starter) | 200 | Indexes in ~50 min. Comfortable. |
| 500 (Pro) | 500 | Indexes in ~100 min. Solid. |
| 1000 (Custom small) | 1000 | Indexes in ~3.3 h. Works; plan upload timing. |
| 5000 (Custom large) | 2000 | Borderline. ~17 h indexing. CompreFace slows. Monitor. |
| 10000+ | — | Needs infra changes (more RQ workers, possibly Gap #2 Path B). |

## Resource ceilings on the current VPS

| Resource | Ceiling | Headroom from Pro 500 |
|----------|---------|------------------------|
| Storage | ~25,000 photos (disk full) | 50× Pro 500 |
| CompreFace subjects | ~50k comfortable, ~100k painful | 33× Pro 500 (× 3 faces/photo) |
| Indexing throughput | 1 RQ worker × ~5 photos/min | Pro 500 indexes in ~100 min |
| Sustained scan rate | ~6 scans/sec (4 uvicorn workers) | ~1000 guests over 3 h event |
| Peak burst scans | ~15 scans/sec before queueing | Brief rushes OK |

## Multi-event capacity (parallel)

Across all live events combined:
- Total active CompreFace subjects: stay under ~50k (10–30 Pro events ×
  500 photos × 3 faces ≈ 15–45k subjects) ✓
- Total active storage: 127 GB free / 2.5 GB per Pro event = ~50 Pro
  events worth of photos before disk pressure (assuming no archival)
- Real ceiling on a busy weekend: **~30 concurrent Pro events** before
  CompreFace + indexing become the bottleneck

## Where CompreFace gets uncomfortable

| Subject count | Status |
|---------------|--------|
| 0–10k | Fast (sub-100 ms 1:N) |
| 10k–50k | Solid (100–300 ms) |
| 50k–100k | Noticeable slowdown (300 ms–1 s) |
| 100k–500k | Painful, may OOM under concurrent load |
| 500k+ | Don't expect it to work well |

Why:
- Linear search — no ANN index in CompreFace, every 1:N walks all subjects.
- All embeddings in compreface-core process memory; single process, no shard.
- No subject-namespace filter in search; we filter event_id post-query
  (wasteful at scale).
- 3-frame scan = 3 sequential HTTP round-trips, no batching.

**Translation**:
- 5000 photos = ~15k subjects → CompreFace happy.
- 50000 photos = ~150k subjects → CompreFace slow.
- 100k+ photos → switch to InsightFace + pgvector (Gap #2 Path B).

## Hardware sizing — "3 events × 1000 photos × 1000 guests each"

Total target workload:
- ~3000 photos / ~15 GB storage
- ~9000 CompreFace subjects
- ~3000 guests, peak ~20 scans/sec if all three events rush together

| Resource | Spec | Why |
|----------|------|-----|
| CPU | 16 vCPU | CompreFace inference + parallel indexing + 8 backend workers |
| RAM | 32 GB | CompreFace-core + Postgres + 8 backend + 4 RQ workers + PIL buffers |
| Storage | 500 GB NVMe SSD | ~6 months of events at this scale; NVMe needed for Postgres + MinIO IOPS |
| Network | 1 Gbps unmetered | Peak ~250 Mbps thumbnail traffic — unmetered matters more than raw bandwidth |

### Provider options

| Provider | Plan | Cost (mo) | Notes |
|----------|------|-----------|-------|
| Hetzner | CPX51 (16 vCPU AMD / 32 GB / 360 GB NVMe) | ~€45 | Best price/perf, EU |
| Contabo | Cloud VPS L+ (16 vCPU / 32 GB / 400 GB NVMe) | ~$35 | Cheapest; already using them |
| OVH | VPS Comfort 3 (8 vCPU / 24 GB / 240 GB SSD) | ~€25 | Budget; CPU may bite during peak burst |
| DigitalOcean | 16 GB AMD Premium (8 vCPU / 320 GB) | ~$84 | Priciest, best ops UX |

**Recommendation**: Contabo Cloud VPS L+ or Hetzner CPX51.

### Required service-level tuning (regardless of hardware)

Hardware alone isn't enough. Without these the spare CPU/RAM is
wasted:

```yaml
# docker-compose.vps.yml
backend:
  command: uvicorn app.main:app --workers 8   # currently 4

worker:
  deploy:
    replicas: 4                                # currently 1

postgres:
  command: >
    postgres
    -c shared_buffers=2GB
    -c effective_cache_size=8GB
    -c max_connections=200

compreface-core:
  cpus: 8.0
```

The current single-VPS setup **can already handle the 3 × 1000 × 1000
workload** after these tuning changes — hardware upgrade is only
needed if you want 5× growth headroom without another migration.

## When to scale beyond a single VPS

- ~25,000 photos total storage → either bigger disk or migrate MinIO
  to a cloud object store backend (S3, Backblaze ~$5/TB/month)
- ~50k CompreFace subjects → consider Gap #2 Path B (replace
  CompreFace with InsightFace + pgvector for sub-100 ms ANN search at
  millions of vectors)
- ~500 concurrent guests sustained → split CompreFace onto its own VPS
  + private network

## Real bottleneck order (what hits first as you grow)

1. **Disk fill from old events** — biggest practical risk. Add retention
   sweeps + monitor at 80% used (~155 GB) on current VPS.
2. **Single RQ worker** during batch uploads. One-line fix (replicas: 4).
3. **CompreFace at >50k subjects**. Solved by Gap #2 Path B.
4. **Backend uvicorn worker count** under concurrent scan burst. One-line fix.
5. **Storage IOPS** during simultaneous indexing + scanning. NVMe handles
   it; spinning disk would not.

## Quick math reference

- 1 photo ≈ 5 MB (avg from real iPhone uploads)
- 1 photo ≈ 3 face rows (typical event)
- 1 scan ≈ 3 frames × ~200 ms CompreFace 1:N call ≈ 600 ms
- 1 scan returns ~10–30 photo URLs × ~30 KB thumb ≈ 0.5–1 MB
- 1 indexer worker ≈ 5 photos/min
- 1 uvicorn worker ≈ 1.5 scans/sec sustained
