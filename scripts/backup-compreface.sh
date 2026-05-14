#!/bin/bash
# CompreFace database backup script.
#
# CompreFace stores its face-recognition state (subjects, embeddings,
# training metadata) in a separate `frs` Postgres database. Losing it
# means every event has to be re-indexed from photos — a multi-hour
# operation for any non-trivial event count. So this MUST be in the
# regular backup rotation alongside the app DB.

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backups/compreface}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/frs_backup_$DATE.dump"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml -f docker-compose.vps.yml}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

mkdir -p "$BACKUP_DIR"

echo -e "${YELLOW}Starting CompreFace backup at $(date)${NC}"

if ! docker compose -f $COMPOSE_FILE ps compreface-postgres-db | grep -q "Up"; then
    echo -e "${RED}Error: compreface-postgres-db container is not running${NC}"
    exit 1
fi

echo -e "${YELLOW}Creating backup: $BACKUP_FILE${NC}"
if docker compose -f $COMPOSE_FILE exec -T compreface-postgres-db \
    pg_dump -U postgres -Fc -d frs > "$BACKUP_FILE"; then
    echo -e "${GREEN}Backup created successfully${NC}"
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}Backup size: $BACKUP_SIZE${NC}"
else
    echo -e "${RED}Error: Backup failed${NC}"
    rm -f "$BACKUP_FILE"
    exit 1
fi

echo -e "${YELLOW}Cleaning up backups older than $RETENTION_DAYS days${NC}"
DELETED_COUNT=$(find "$BACKUP_DIR" -name "frs_backup_*.dump" -mtime +$RETENTION_DAYS -delete -print | wc -l)
echo -e "${GREEN}Deleted $DELETED_COUNT old backup(s)${NC}"

echo -e "${YELLOW}Recent backups:${NC}"
ls -lh "$BACKUP_DIR" | tail -n 5

echo -e "${GREEN}CompreFace backup completed at $(date)${NC}"
