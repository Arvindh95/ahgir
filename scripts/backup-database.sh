#!/bin/bash
# Database backup script for PicUr's application DB (picur).
#
# Uses pg_dump custom format (-Fc) so the matching `restore-database.sh`
# can use `pg_restore --clean --if-exists` to do a true overwrite. Plain
# SQL piped into psql on a populated DB fails with duplicate-key / object
# errors on existing rows.

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/picur_backup_$DATE.dump"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml -f docker-compose.vps.yml}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

echo -e "${YELLOW}Starting database backup at $(date)${NC}"

# Check if PostgreSQL container is running
if ! docker compose -f $COMPOSE_FILE ps postgres | grep -q "Up"; then
    echo -e "${RED}Error: PostgreSQL container is not running${NC}"
    exit 1
fi

# Create backup (custom format, internally compressed by pg_dump)
echo -e "${YELLOW}Creating backup: $BACKUP_FILE${NC}"
if docker compose -f $COMPOSE_FILE exec -T postgres \
    pg_dump -U picur -Fc -d picur > "$BACKUP_FILE"; then
    echo -e "${GREEN}Backup created successfully${NC}"

    # Get backup size
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}Backup size: $BACKUP_SIZE${NC}"
else
    echo -e "${RED}Error: Backup failed${NC}"
    rm -f "$BACKUP_FILE"
    exit 1
fi

# Clean up old backups
echo -e "${YELLOW}Cleaning up backups older than $RETENTION_DAYS days${NC}"
DELETED_COUNT=$(find "$BACKUP_DIR" -name "picur_backup_*.dump" -mtime +$RETENTION_DAYS -delete -print | wc -l)
# Also clean up legacy .sql.gz from before the format switch.
find "$BACKUP_DIR" -name "picur_backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
echo -e "${GREEN}Deleted $DELETED_COUNT old backup(s)${NC}"

# List recent backups
echo -e "${YELLOW}Recent backups:${NC}"
ls -lh "$BACKUP_DIR" | tail -n 5

echo -e "${GREEN}Database backup completed at $(date)${NC}"
