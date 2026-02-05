# PicUr Deployment Guide

This guide covers deploying PicUr in production environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Deployment Steps](#deployment-steps)
- [SSL/TLS Configuration](#ssltls-configuration)
- [Backup Procedures](#backup-procedures)
- [Monitoring and Maintenance](#monitoring-and-maintenance)
- [Troubleshooting](#troubleshooting)
- [Scaling](#scaling)

## Prerequisites

### System Requirements

- **Operating System**: Linux (Ubuntu 22.04 LTS recommended)
- **Docker**: Version 24.0 or higher
- **Docker Compose**: Version 2.20 or higher
- **RAM**: Minimum 8GB (16GB recommended for production)
- **CPU**: Minimum 4 cores (8 cores recommended)
- **Storage**: Minimum 100GB SSD (depends on photo volume)
- **Network**: Public IP address with ports 80 and 443 accessible

### Domain Configuration

1. Register a domain name (e.g., `picur.example.com`)
2. Configure DNS A record pointing to your server's IP address
3. Wait for DNS propagation (can take up to 48 hours)

## Environment Variables

### Required Variables

Copy the production environment template and configure:

```bash
cp .env.production.example .env.production
```

Edit `.env.production` and set the following **required** variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | PostgreSQL database password | Strong random password |
| `MINIO_ROOT_USER` | MinIO admin username | `minioadmin` |
| `MINIO_ROOT_PASSWORD` | MinIO admin password | Strong random password |
| `JWT_SECRET_KEY` | JWT signing secret | Generate with `openssl rand -hex 32` |
| `DOMAIN` | Your domain name | `picur.example.com` |
| `NEXT_PUBLIC_API_URL` | Public API URL | `https://picur.example.com/api` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_USER` | PostgreSQL username | `picur` |
| `POSTGRES_DB` | PostgreSQL database name | `picur` |
| `JWT_EXPIRATION_HOURS` | JWT token expiration | `24` |
| `LOG_LEVEL` | Application log level | `INFO` |
| `BACKEND_WORKERS` | Uvicorn worker processes | `4` |
| `WORKER_REPLICAS` | Number of RQ worker containers | `2` |
| `CORS_ORIGINS` | Allowed CORS origins | `*` |

### Generating Secrets

Generate strong secrets for production:

```bash
# JWT Secret Key
openssl rand -hex 32

# PostgreSQL Password
openssl rand -base64 32

# MinIO Password
openssl rand -base64 32
```

## Deployment Steps

### 1. Initial Setup

Clone the repository and navigate to the project directory:

```bash
git clone https://github.com/yourusername/picur.git
cd picur
```

### 2. Configure Environment

```bash
# Copy and edit production environment file
cp .env.production.example .env.production
nano .env.production

# Set proper permissions
chmod 600 .env.production
```

### 3. Build and Start Services

```bash
# Build all services
docker-compose -f docker-compose.production.yml build

# Start all services
docker-compose -f docker-compose.production.yml --env-file .env.production up -d

# Check service status
docker-compose -f docker-compose.production.yml ps
```

### 4. Run Database Migrations

```bash
# Run Alembic migrations
docker-compose -f docker-compose.production.yml exec backend alembic upgrade head

# Verify database tables
docker-compose -f docker-compose.production.yml exec postgres psql -U picur -d picur -c "\dt"
```

### 5. Initialize MinIO Bucket

```bash
# The application will create the bucket automatically on first upload
# Or manually create it:
docker-compose -f docker-compose.production.yml exec backend python -c "
from app.storage import get_minio_client
client = get_minio_client()
if not client.bucket_exists('photos'):
    client.make_bucket('photos')
    print('Bucket created')
"
```

### 6. Verify Deployment

```bash
# Check all services are healthy
docker-compose -f docker-compose.production.yml ps

# Test health endpoint
curl https://yourdomain.com/health

# Check logs
docker-compose -f docker-compose.production.yml logs -f
```

### 7. Create First Admin User

Access the application at `https://yourdomain.com` and register the first admin account.

## SSL/TLS Configuration

### Automatic HTTPS with Caddy

Caddy automatically obtains and renews SSL certificates from Let's Encrypt. No manual configuration needed!

**Requirements:**
- Domain must point to your server's public IP
- Ports 80 and 443 must be accessible from the internet
- Server must be reachable at the configured domain

**Verification:**

```bash
# Check Caddy logs for certificate acquisition
docker-compose -f docker-compose.production.yml logs caddy | grep -i certificate

# Test HTTPS
curl -I https://yourdomain.com
```

### Manual Certificate Configuration

If you have existing certificates:

1. Place certificates in `./certs/` directory:
   - `fullchain.pem` (certificate + chain)
   - `privkey.pem` (private key)

2. Update `Caddyfile.production`:

```caddyfile
yourdomain.com {
    tls /certs/fullchain.pem /certs/privkey.pem
    # ... rest of configuration
}
```

3. Mount certificates in `docker-compose.production.yml`:

```yaml
caddy:
  volumes:
    - ./certs:/certs:ro
```

## Backup Procedures

### Database Backup

Create automated database backups:

```bash
#!/bin/bash
# backup-database.sh

BACKUP_DIR="/backups/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/picur_backup_$DATE.sql.gz"

mkdir -p $BACKUP_DIR

# Create backup
docker-compose -f docker-compose.production.yml exec -T postgres \
  pg_dump -U picur picur | gzip > $BACKUP_FILE

# Keep only last 30 days
find $BACKUP_DIR -name "picur_backup_*.sql.gz" -mtime +30 -delete

echo "Backup completed: $BACKUP_FILE"
```

Schedule with cron:

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /path/to/backup-database.sh >> /var/log/picur-backup.log 2>&1
```

### Database Restore

```bash
# Stop services
docker-compose -f docker-compose.production.yml stop backend worker

# Restore from backup
gunzip -c /backups/postgres/picur_backup_YYYYMMDD_HHMMSS.sql.gz | \
  docker-compose -f docker-compose.production.yml exec -T postgres \
  psql -U picur picur

# Start services
docker-compose -f docker-compose.production.yml start backend worker
```

### MinIO Backup

Backup MinIO data:

```bash
#!/bin/bash
# backup-minio.sh

BACKUP_DIR="/backups/minio"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/minio_backup_$DATE.tar.gz"

mkdir -p $BACKUP_DIR

# Create backup
docker run --rm \
  --volumes-from picur-minio \
  -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/minio_backup_$DATE.tar.gz /data

# Keep only last 30 days
find $BACKUP_DIR -name "minio_backup_*.tar.gz" -mtime +30 -delete

echo "MinIO backup completed: $BACKUP_FILE"
```

### MinIO Restore

```bash
# Stop MinIO
docker-compose -f docker-compose.production.yml stop minio

# Restore from backup
docker run --rm \
  --volumes-from picur-minio \
  -v /backups/minio:/backup \
  alpine sh -c "cd / && tar xzf /backup/minio_backup_YYYYMMDD_HHMMSS.tar.gz"

# Start MinIO
docker-compose -f docker-compose.production.yml start minio
```

### Full System Backup Script

```bash
#!/bin/bash
# backup-all.sh

BACKUP_ROOT="/backups"
DATE=$(date +%Y%m%d_%H%M%S)

echo "Starting full backup at $DATE"

# Backup database
./backup-database.sh

# Backup MinIO
./backup-minio.sh

# Backup configuration files
tar czf $BACKUP_ROOT/config_backup_$DATE.tar.gz \
  .env.production \
  Caddyfile.production \
  docker-compose.production.yml

echo "Full backup completed at $(date +%Y%m%d_%H%M%S)"
```

## Monitoring and Maintenance

### Health Checks

Monitor service health:

```bash
# Check all services
docker-compose -f docker-compose.production.yml ps

# Check specific service logs
docker-compose -f docker-compose.production.yml logs -f backend
docker-compose -f docker-compose.production.yml logs -f worker

# Check health endpoint
curl https://yourdomain.com/health
```

### Log Management

View and manage logs:

```bash
# View all logs
docker-compose -f docker-compose.production.yml logs

# Follow logs in real-time
docker-compose -f docker-compose.production.yml logs -f

# View specific service logs
docker-compose -f docker-compose.production.yml logs backend

# View last 100 lines
docker-compose -f docker-compose.production.yml logs --tail=100

# Clear logs (be careful!)
docker-compose -f docker-compose.production.yml logs --no-log-prefix > /dev/null
```

### Resource Monitoring

Monitor resource usage:

```bash
# Container stats
docker stats

# Disk usage
docker system df

# Volume usage
docker volume ls
du -sh /var/lib/docker/volumes/*
```

### Database Maintenance

Regular maintenance tasks:

```bash
# Vacuum database
docker-compose -f docker-compose.production.yml exec postgres \
  psql -U picur -d picur -c "VACUUM ANALYZE;"

# Check database size
docker-compose -f docker-compose.production.yml exec postgres \
  psql -U picur -d picur -c "SELECT pg_size_pretty(pg_database_size('picur'));"

# Check table sizes
docker-compose -f docker-compose.production.yml exec postgres \
  psql -U picur -d picur -c "
    SELECT schemaname, tablename, 
           pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
    FROM pg_tables 
    WHERE schemaname = 'public' 
    ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
  "
```

### Updates and Upgrades

Update the application:

```bash
# Pull latest code
git pull origin main

# Rebuild services
docker-compose -f docker-compose.production.yml build

# Stop services
docker-compose -f docker-compose.production.yml down

# Start with new images
docker-compose -f docker-compose.production.yml --env-file .env.production up -d

# Run migrations
docker-compose -f docker-compose.production.yml exec backend alembic upgrade head
```

## Troubleshooting

### Common Issues

#### Services Won't Start

```bash
# Check logs
docker-compose -f docker-compose.production.yml logs

# Check service status
docker-compose -f docker-compose.production.yml ps

# Restart specific service
docker-compose -f docker-compose.production.yml restart backend
```

#### Database Connection Issues

```bash
# Check PostgreSQL is running
docker-compose -f docker-compose.production.yml ps postgres

# Test database connection
docker-compose -f docker-compose.production.yml exec postgres \
  psql -U picur -d picur -c "SELECT 1;"

# Check database logs
docker-compose -f docker-compose.production.yml logs postgres
```

#### MinIO Connection Issues

```bash
# Check MinIO is running
docker-compose -f docker-compose.production.yml ps minio

# Test MinIO health
curl http://localhost:9000/minio/health/live

# Check MinIO logs
docker-compose -f docker-compose.production.yml logs minio
```

#### SSL Certificate Issues

```bash
# Check Caddy logs
docker-compose -f docker-compose.production.yml logs caddy

# Verify DNS is correct
nslookup yourdomain.com

# Test port accessibility
curl -I http://yourdomain.com
```

#### Worker Not Processing Jobs

```bash
# Check worker logs
docker-compose -f docker-compose.production.yml logs worker

# Check Redis connection
docker-compose -f docker-compose.production.yml exec redis redis-cli ping

# Check job queue
docker-compose -f docker-compose.production.yml exec redis redis-cli llen rq:queue:default
```

### Performance Issues

#### High CPU Usage

```bash
# Check container stats
docker stats

# Scale workers
docker-compose -f docker-compose.production.yml up -d --scale worker=4

# Check slow queries
docker-compose -f docker-compose.production.yml exec postgres \
  psql -U picur -d picur -c "
    SELECT query, calls, total_time, mean_time 
    FROM pg_stat_statements 
    ORDER BY mean_time DESC 
    LIMIT 10;
  "
```

#### High Memory Usage

```bash
# Check memory usage
docker stats

# Restart services to clear memory
docker-compose -f docker-compose.production.yml restart

# Adjust resource limits in docker-compose.production.yml
```

#### Slow Face Recognition

```bash
# Scale up workers
docker-compose -f docker-compose.production.yml up -d --scale worker=4

# Check worker logs for errors
docker-compose -f docker-compose.production.yml logs worker

# Monitor job processing
docker-compose -f docker-compose.production.yml exec redis redis-cli llen rq:queue:default
```

## Scaling

### Horizontal Scaling

Scale services based on load:

```bash
# Scale backend API
docker-compose -f docker-compose.production.yml up -d --scale backend=3

# Scale workers
docker-compose -f docker-compose.production.yml up -d --scale worker=4

# Scale frontend
docker-compose -f docker-compose.production.yml up -d --scale frontend=2
```

### Vertical Scaling

Adjust resource limits in `docker-compose.production.yml`:

```yaml
backend:
  deploy:
    resources:
      limits:
        cpus: '4'
        memory: 4G
```

### Load Balancing

Caddy automatically load balances across multiple backend/frontend instances.

### Database Optimization

```bash
# Add indexes for common queries
docker-compose -f docker-compose.production.yml exec postgres \
  psql -U picur -d picur -c "
    CREATE INDEX CONCURRENTLY idx_images_event_status 
    ON images(event_id, status);
  "

# Analyze query performance
docker-compose -f docker-compose.production.yml exec postgres \
  psql -U picur -d picur -c "EXPLAIN ANALYZE SELECT * FROM images WHERE event_id = 'uuid';"
```

## Security Best Practices

1. **Change Default Passwords**: Always use strong, unique passwords
2. **Restrict Network Access**: Use firewall rules to limit access
3. **Regular Updates**: Keep Docker images and system packages updated
4. **Monitor Logs**: Regularly review logs for suspicious activity
5. **Backup Regularly**: Automate backups and test restore procedures
6. **Use HTTPS**: Always use SSL/TLS in production
7. **Limit CORS**: Restrict CORS origins to your domain only
8. **Secure Environment Files**: Set proper permissions on `.env.production`

## Support

For issues and questions:
- GitHub Issues: https://github.com/yourusername/picur/issues
- Documentation: https://github.com/yourusername/picur/wiki
- Email: support@yourdomain.com
