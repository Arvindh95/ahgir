#!/bin/bash
# MinIO backup script for PicUr
# This script creates a compressed backup of MinIO data

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backups/minio}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/minio_backup_$DATE.tar.gz"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

echo -e "${YELLOW}Starting MinIO backup at $(date)${NC}"

# Check if MinIO container is running
if ! docker ps | grep -q picur-minio; then
    echo -e "${RED}Error: MinIO container is not running${NC}"
    exit 1
fi

# Create backup
echo -e "${YELLOW}Creating backup: $BACKUP_FILE${NC}"
if docker run --rm \
    --volumes-from picur-minio \
    -v "$BACKUP_DIR:/backup" \
    alpine tar czf "/backup/minio_backup_$DATE.tar.gz" /data; then
    echo -e "${GREEN}Backup created successfully${NC}"
    
    # Get backup size
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}Backup size: $BACKUP_SIZE${NC}"
else
    echo -e "${RED}Error: Backup failed${NC}"
    exit 1
fi

# Clean up old backups
echo -e "${YELLOW}Cleaning up backups older than $RETENTION_DAYS days${NC}"
DELETED_COUNT=$(find "$BACKUP_DIR" -name "minio_backup_*.tar.gz" -mtime +$RETENTION_DAYS -delete -print | wc -l)
echo -e "${GREEN}Deleted $DELETED_COUNT old backup(s)${NC}"

# List recent backups
echo -e "${YELLOW}Recent backups:${NC}"
ls -lh "$BACKUP_DIR" | tail -n 5

echo -e "${GREEN}MinIO backup completed at $(date)${NC}"
