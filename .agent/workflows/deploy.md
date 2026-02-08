---
description: How to deploy changes to the production server
---

# Deploy to Production

## Prerequisites
- SSH access to the production server (root@72.62.193.80)
- Changes committed and pushed to `main` branch

## Steps

1. SSH into the production server:
```bash
ssh root@72.62.193.80
```

2. Navigate to the project directory:
```bash
cd /root/ahgir
```

3. Pull the latest changes:
```bash
git pull origin main
```

4. Rebuild the changed service(s) (replace `<service>` with `frontend`, `backend`, or `worker`):
```bash
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml build --no-cache <service>
```

5. Restart the service(s):
```bash
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml up -d <service>
```

## Service Options

| Service | When to rebuild |
|---------|-----------------|
| `frontend` | When frontend code changes |
| `backend` | When backend/API code changes |
| `worker` | When background worker code changes |

## Example: Deploying Backend Changes

```bash
ssh root@72.62.193.80
cd /root/ahgir
git pull origin main
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml build --no-cache backend
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml up -d backend
```
