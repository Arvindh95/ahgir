#!/bin/bash
# Full system backup script for PicUr
# This script backs up database, MinIO data, and configuration files

set -e

# Configuration
BACKUP_ROOT="${BACKUP_DIR:-/backups}"
DATE=$(date +%Y%m%d_%H%M%S)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}PicUr Full System Backup${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Starting full backup at $(date)${NC}"
echo ""

# Backup database
echo -e "${BLUE}[1/3] Backing up database...${NC}"
if bash "$SCRIPT_DIR/backup-database.sh"; then
    echo -e "${GREEN}✓ Database backup completed${NC}"
else
    echo -e "${RED}✗ Database backup failed${NC}"
    exit 1
fi
echo ""

# Backup MinIO
echo -e "${BLUE}[2/3] Backing up MinIO data...${NC}"
if bash "$SCRIPT_DIR/backup-minio.sh"; then
    echo -e "${GREEN}✓ MinIO backup completed${NC}"
else
    echo -e "${RED}✗ MinIO backup failed${NC}"
    exit 1
fi
echo ""

# Backup configuration files
echo -e "${BLUE}[3/3] Backing up configuration files...${NC}"
CONFIG_BACKUP_DIR="$BACKUP_ROOT/config"
mkdir -p "$CONFIG_BACKUP_DIR"
CONFIG_BACKUP_FILE="$CONFIG_BACKUP_DIR/config_backup_$DATE.tar.gz"

cd "$PROJECT_DIR"
if tar czf "$CONFIG_BACKUP_FILE" \
    .env.production \
    Caddyfile \
    Caddyfile.prod \
    docker-compose.yml \
    docker-compose.prod.yml \
    2>/dev/null; then
    echo -e "${GREEN}✓ Configuration backup completed${NC}"
    CONFIG_SIZE=$(du -h "$CONFIG_BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}  Backup size: $CONFIG_SIZE${NC}"
else
    echo -e "${YELLOW}⚠ Some configuration files may be missing${NC}"
fi

# Clean up old config backups
find "$CONFIG_BACKUP_DIR" -name "config_backup_*.tar.gz" -mtime +30 -delete
echo ""

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Full backup completed at $(date)${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Backup locations:${NC}"
echo -e "  Database: $BACKUP_ROOT/postgres/"
echo -e "  MinIO:    $BACKUP_ROOT/minio/"
echo -e "  Config:   $CONFIG_BACKUP_DIR/"
echo ""
echo -e "${YELLOW}Total backup size:${NC}"
du -sh "$BACKUP_ROOT"
