# PicUr Migration & Scale Runbook

How to move PicUr to a bigger box, swap regions, or split out individual
services if any one of them becomes the bottleneck. Treat this as a
runbook — execute top-to-bottom, don't improvise during an outage.

Current production target: Contabo VPS `173.212.247.3`, 8 vCPU / 24GB / 200GB SSD,
single host, all services in one docker-compose stack. Single point of failure.

---

## Pre-flight Inventory

What lives where on the current VPS:

| Component | Path / Volume | Why it matters |
|---|---|---|
| App code (git checkout) | `/opt/ahgir` | Code only; replaceable with `git clone` |
| Production env | `/opt/ahgir/.env.production` | **Has secrets** — copy via `scp`, never commit |
| Postgres data | named volume `ahgir_postgres_data` | Source of truth for all subscriptions, events, users, audit log |
| MinIO photos | named volume `ahgir_minio_data` | Original + thumbnail photo bytes |
| CompreFace embeddings | named volume `compreface_postgres_data` | Face vectors. Lose this = re-index every event |
| Cloudflare Origin TLS cert | `/etc/ssl/picur.my/{fullchain,privkey}.pem` | 15-year cert; copy to new host |
| Host nginx vhost | `/etc/nginx/sites-enabled/picur` | TLS termination + routing |
| Brevo SMTP creds | in `.env.production` | Outbound email |
| Stripe live keys | in `.env.production` | Billing — rotate if exposed |
| Redis | named volume `ahgir_redis_data` | RQ queue state. Tolerable to lose (jobs re-enqueue), but in-flight scans fail |

The DNS is on Cloudflare. Set TTL to 60s on the `picur.my` A record at least
24 hours before any planned cutover.

---

## Scenario A: Like-for-Like Migration (Same Topology, Bigger Host)

When to use: you outgrew Contabo's 8 vCPU / 24GB and want a beefier single VPS.
Indicators: `/health/load` verdict consistently `orange`+, `oldest_pending_age_minutes` > 5 during normal load.

**Estimated effort:** 1 evening (3-4 hours), most of it waiting for transfers.
Customer-visible downtime: ~5-10 minutes if you preload + DNS-flip cleanly.

### Step 1 — Provision new host

```bash
# Pick a host. Recommended for next-tier:
#   Contabo VPS XL: 16 vCPU / 60GB / 500GB SSD ~ $25/mo
#   Hetzner CCX23: 8 dedicated vCPU / 32GB / 240GB ~ $40/mo (better CPU)
#   Vultr/Linode equivalent ~ $40-80/mo
# Pick the same OS as current (Ubuntu 24.04).
```

On the new host:

```bash
apt update && apt install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx
systemctl enable --now docker
mkdir -p /opt
```

Set up your SSH key on the new host. From your laptop:

```bash
ssh-copy-id root@<new-ip>
```

### Step 2 — Push the latest code

```bash
ssh root@<new-ip>
cd /opt
git clone https://github.com/Arvindh95/ahgir.git
cd ahgir
git checkout main
```

### Step 3 — Copy secrets and TLS

From your laptop (NOT through GitHub — these are secrets):

```bash
scp root@173.212.247.3:/opt/ahgir/.env.production root@<new-ip>:/opt/ahgir/.env.production
scp -r root@173.212.247.3:/etc/ssl/picur.my root@<new-ip>:/etc/ssl/
ssh root@<new-ip> "chmod 600 /opt/ahgir/.env.production /etc/ssl/picur.my/privkey.pem"
```

### Step 4 — Snapshot data on the OLD host

```bash
ssh root@173.212.247.3
cd /opt/ahgir

# Postgres dump (PicUr app data)
docker exec picur-postgres pg_dump -U picur -d picur -Fc -f /tmp/picur.dump
docker cp picur-postgres:/tmp/picur.dump /tmp/picur.dump

# CompreFace's separate Postgres (face embeddings)
docker exec compreface-postgres-db pg_dump -U compreface -d frs -Fc -f /tmp/frs.dump
docker cp compreface-postgres-db:/tmp/frs.dump /tmp/frs.dump

# MinIO bucket (raw + thumb photos)
docker exec picur-minio mc alias set local http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" 2>/dev/null
docker exec picur-minio mc mirror --quiet /data/photos /tmp/photos-snapshot
docker cp picur-minio:/tmp/photos-snapshot /tmp/photos-snapshot
tar -czf /tmp/photos.tar.gz -C /tmp photos-snapshot
```

### Step 5 — Transfer to new host

```bash
# From OLD VPS, push to NEW VPS
scp /tmp/picur.dump /tmp/frs.dump /tmp/photos.tar.gz root@<new-ip>:/tmp/
```

For events with thousands of photos this can be slow. Run it in `tmux` or
`screen` so an SSH disconnect doesn't kill the transfer.

### Step 6 — Bring up base services on NEW host

```bash
ssh root@<new-ip>
cd /opt/ahgir

# Start ONLY data services first so we can restore into them
docker compose -f docker-compose.yml -f docker-compose.vps.yml --env-file .env.production up -d postgres minio redis compreface-postgres-db
sleep 10
```

### Step 7 — Restore data

```bash
# Restore PicUr DB
docker cp /tmp/picur.dump picur-postgres:/tmp/picur.dump
docker exec picur-postgres pg_restore -U picur -d picur --clean --if-exists /tmp/picur.dump

# Restore CompreFace embeddings
docker cp /tmp/frs.dump compreface-postgres-db:/tmp/frs.dump
docker exec compreface-postgres-db pg_restore -U compreface -d frs --clean --if-exists /tmp/frs.dump

# Restore MinIO photos
mkdir -p /tmp/photos-restore
tar -xzf /tmp/photos.tar.gz -C /tmp/photos-restore
docker cp /tmp/photos-restore/photos-snapshot picur-minio:/data/photos
```

Verify rows match:

```bash
docker exec picur-postgres psql -U picur -d picur -c "SELECT COUNT(*) FROM events; SELECT COUNT(*) FROM images; SELECT COUNT(*) FROM users;"
```

Compare with OLD host's counts.

### Step 8 — Bring up the rest

```bash
docker compose -f docker-compose.yml -f docker-compose.vps.yml --env-file .env.production up -d
docker compose ps
```

### Step 9 — Configure host nginx + TLS

```bash
# Copy the picur vhost from old host
scp root@173.212.247.3:/etc/nginx/sites-enabled/picur root@<new-ip>:/etc/nginx/sites-available/picur
ssh root@<new-ip>
ln -s /etc/nginx/sites-available/picur /etc/nginx/sites-enabled/picur
nginx -t && systemctl reload nginx
```

### Step 10 — Smoke test on NEW host (still hitting old DNS)

From your laptop, test by overriding DNS locally:

```bash
# Edit /etc/hosts (or C:\Windows\System32\drivers\etc\hosts)
<new-ip>  picur.my

# Then
curl -sS https://picur.my/api/health
curl -sS https://picur.my/api/payments/config
```

If both return 200 with expected data, you're cleared for cutover.

### Step 11 — DNS cutover

In Cloudflare dashboard:
- DNS → A record `picur.my` → change IP from `173.212.247.3` to `<new-ip>`
- TTL: keep at 60s
- Save

Watch:
```bash
# From laptop
while true; do dig +short picur.my; sleep 5; done
```

Within 1-2 minutes most traffic should be hitting the new host.

### Step 12 — Verify with real probes

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://picur.my/api/health
ssh root@<new-ip> "docker exec -e PYTHONPATH=/app picur-backend python /app/scripts/probe_health_load.py"
```

Run an end-to-end billing test (live mode) only if you want to pay
for it — alternative: skip until first real customer transacts.

### Step 13 — Update Stripe webhook IP whitelist

Stripe doesn't whitelist your IP. Skip.

### Step 14 — Decommission old host

After 24-48h with no errors:

```bash
ssh root@173.212.247.3
docker compose down
# Snapshot the VM in your provider's console as a "just-in-case" backup
# Then power down or destroy the VPS
```

### Rollback

If anything's broken on the new host:

```bash
# Cloudflare DNS A record → revert to 173.212.247.3
# Old host is still running with original data; it will receive traffic again within 1-2 min.
```

The old host's Postgres only diverges after cutover if subscriptions
fired during the new-host window. If you cut back, those new
subscriptions exist on new-host DB only. Reconcile manually
via Stripe Dashboard webhook event resends.

---

## Scenario B: Split Architecture (Beat the Single-Host Bottleneck)

When to use: your bottleneck is a specific component, not overall capacity.

| Symptom (from `/health/load`) | Bottleneck | Fix |
|---|---|---|
| `oldest_pending_age_minutes` consistently >5 with 1+ active events | Indexing CPU (CompreFace) | Move CompreFace to GPU box |
| `compreface.ping_ms` > 500 under load | Indexing CPU (CompreFace) | Same |
| `system.load_per_core_1m` > 0.85 with low queue depth | App CPU | Scale FastAPI / worker replicas |
| `redis.used_memory_mb` > 200 | Job retention TTLs | Lower `result_ttl` in `app/queue.py` |
| Postgres slow (`pg_stat_activity` shows long queries) | DB CPU | Move Postgres to managed service |
| MinIO disk approaching full | Storage | Move to S3 |

### B1. Move CompreFace to a dedicated GPU box

Why first: face indexing is the most CPU-heavy job, GPU gives 10-50x speedup.

1. Provision GPU VPS (Vast.ai RTX 3060 ~$80/mo, AWS T4 ~$200/mo, Asia-region preferred)
2. SSH in, install Docker + nvidia-container-toolkit
3. Pull CompreFace **GPU build:** `exadel/compreface-core:1.2.0-gpu` (and matching api/admin images)
4. Run only the 3 CompreFace services + their postgres (use `docker-compose.prod.yml` as starting point)
5. Restore the CompreFace postgres dump from current setup
6. Open ports 8080 (compreface-api) on internal network only
7. On the **app VPS**, change `COMPREFACE_API_URL` in `.env.production` to point at the GPU box's internal IP
8. Restart backend + worker
9. The face_indexing queue will start draining 10-50x faster
10. Tune `prediction_count` higher if you want — GPU laughs at it

### B2. Move Postgres to managed (RDS / Supabase / Neon)

When: DB CPU pegged or you want point-in-time-recovery and zero-downtime upgrades.

1. Provision managed Postgres in same region (RDS db.t4g.medium, Supabase pro, Neon)
2. Enable `pgvector` and `uuid-ossp` extensions
3. `pg_dump -Fc` from current → restore to managed
4. Update `DATABASE_URL` in `.env.production`
5. Recreate the backend + worker containers (no rebuild needed, env-only change)
6. Drop the picur-postgres container from compose (keep the volume around for one week as backup)

Cost: ~$30-100/mo managed vs $0 on-VPS, but you get backups and HA.

### B3. Move MinIO to S3 (or Cloudflare R2)

When: photo storage > 100GB or you want CDN serving for thumbnails.

R2 is cheap (no egress fee) and S3-compatible — easiest swap:

1. Cloudflare R2 → create bucket `picur-photos`
2. Generate access key/secret
3. Run `mc mirror` from current MinIO to R2
4. Update `.env.production`:
   ```
   MINIO_ENDPOINT=<account>.r2.cloudflarestorage.com
   MINIO_EXTERNAL_ENDPOINT=<bucket>.r2.dev
   MINIO_ACCESS_KEY=<r2-access-key>
   MINIO_SECRET_KEY=<r2-secret-key>
   MINIO_SECURE=true
   MINIO_EXTERNAL_SECURE=true
   ```
5. Recreate backend + worker
6. Test photo upload + scan (signed URL flow should work since R2 supports presigned URLs)
7. Drop the picur-minio container from compose

### B4. Scale FastAPI / worker

In `docker-compose.prod.yml` add `deploy: replicas: N`. Already wired for `compreface-api` to run 2 replicas; same pattern for `backend` and `worker`. Host nginx already handles backend load with `upstream` block — add more entries.

---

## Scenario C: Disaster Recovery (Current Host Hard-Crashes)

If `173.212.247.3` is gone and you have NO snapshot:

- **App code**: clone from GitHub, fully recoverable
- **`.env.production` secrets**: lost unless you backed up. **Action: now.** Copy `.env.production` to a password manager / encrypted local backup. Same for `/etc/ssl/picur.my/privkey.pem`.
- **Postgres data**: lost. All subscriptions need to be reconstructed from Stripe Dashboard (webhook events are queryable for 30 days, can re-fire to rebuild state).
- **MinIO photos**: lost. Customer photos gone. **Action: now.** Set up a daily off-site backup.
- **CompreFace embeddings**: lost. All events must re-index.

### Off-site backup plan (TODO if not done)

Two minimum viable options:

**Option A — daily rsync to second cheap VPS or NAS:**

```bash
# On current host, /opt/ahgir/scripts/backup-offsite.sh
#!/usr/bin/env bash
set -euo pipefail
TS=$(date +%Y%m%d_%H%M%S)
docker exec picur-postgres pg_dump -U picur -d picur -Fc -f /tmp/picur-$TS.dump
docker exec compreface-postgres-db pg_dump -U compreface -d frs -Fc -f /tmp/frs-$TS.dump
rsync -az /tmp/picur-$TS.dump /tmp/frs-$TS.dump backup-host:/backups/
docker cp picur-minio:/data/photos /tmp/photos-$TS
rsync -az /tmp/photos-$TS/ backup-host:/backups/photos/
rm -rf /tmp/picur-$TS.dump /tmp/frs-$TS.dump /tmp/photos-$TS
```

Add to root crontab: `0 3 * * * /opt/ahgir/scripts/backup-offsite.sh`

**Option B — managed backup service:**
- Hetzner Storage Box: $5/mo for 1TB, mount via SFTP/SSHFS
- Backblaze B2: pay-per-GB, $0.005/GB/month
- AWS S3 Glacier: cheaper for archive

---

## Cutover Checklist (Use This During Real Migration)

- [ ] Cloudflare DNS TTL set to 60s, ≥24h before cutover
- [ ] New host provisioned and reachable
- [ ] Latest `main` checked out on new host
- [ ] `.env.production` copied (chmod 600)
- [ ] TLS cert + key copied
- [ ] Postgres dump (picur DB) transferred + restored
- [ ] CompreFace postgres dump transferred + restored
- [ ] MinIO photos transferred + restored
- [ ] Row counts match between old and new host (events, images, users)
- [ ] Containers up and healthy on new host
- [ ] Host nginx vhost copied + reloaded
- [ ] Stripe webhook still pointing at picur.my (no change — DNS handles routing)
- [ ] Local hosts-file probe of new host returns 200
- [ ] DNS A record updated in Cloudflare
- [ ] DNS propagation watched (`dig +short picur.my`)
- [ ] Public probe returns 200 from new IP
- [ ] `/health/load` verdict green from new host
- [ ] Old host kept running for 48h before decommission

---

## Cost Snapshot (As of 2026-05)

Current: Contabo VPS S, ~$5/mo. Reasonable for beta.

Estimated next steps:

| Tier | Monthly | Capacity ceiling |
|---|---|---|
| Now: Contabo S, all-in-one | $5 | ~5 simultaneous events, low concurrent scans |
| Bigger Contabo XL | $25 | ~30 events, decent scan concurrency |
| Hetzner CCX23 | $40 | ~50 events, faster CPU per scan |
| Hetzner + GPU CompreFace box | $40 + $80 | ~200 events, sub-second scan latency |
| Managed Postgres (RDS/Supabase) | +$30 | Removes DB SPOF |
| Cloudflare R2 (storage) | +$1.50/100GB stored | Removes disk concerns, near-zero egress |

Rule of thumb: don't pre-buy capacity. Watch `/health/load`. Scale the
specific component that's red, not the whole stack.
