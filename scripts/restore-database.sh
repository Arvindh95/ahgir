#!/bin/bash
# Database restore script for PicUr
# This script restores a PostgreSQL database from a backup file

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml -f docker-compose.prod.yml}"

# Check if backup file is provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: Backup file not specified${NC}"
    echo -e "${YELLOW}Usage: $0 <backup_file.sql.gz>${NC}"
    echo ""
    echo -e "${YELLOW}Available backups:${NC}"
    ls -lh /backups/postgres/*.sql.gz 2>/dev/null || echo "No backups found"
    exit 1
fi

BACKUP_FILE="$1"

# Check if backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}Error: Backup file not found: $BACKUP_FILE${NC}"
    exit 1
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}PicUr Database Restore${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Backup file: $BACKUP_FILE${NC}"
echo -e "${YELLOW}Backup size: $(du -h "$BACKUP_FILE" | cut -f1)${NC}"
echo ""

# Confirmation prompt
echo -e "${RED}WARNING: This will overwrite the current database!${NC}"
read -p "Are you sure you want to continue? (yes/no): " -r
echo
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo -e "${YELLOW}Restore cancelled${NC}"
    exit 0
fi

# Stop backend and worker services
echo -e "${YELLOW}Stopping backend and worker services...${NC}"
docker compose -f $COMPOSE_FILE stop backend worker
echo -e "${GREEN}✓ Services stopped${NC}"
echo ""

# Restore database
echo -e "${YELLOW}Restoring database...${NC}"
if gunzip -c "$BACKUP_FILE" | \
    docker compose -f $COMPOSE_FILE exec -T postgres \
    psql -U picur picur; then
    echo -e "${GREEN}✓ Database restored successfully${NC}"
else
    echo -e "${RED}✗ Database restore failed${NC}"
    echo -e "${YELLOW}Starting services...${NC}"
    docker compose -f $COMPOSE_FILE start backend worker
    exit 1
fi
echo ""

# Start services
echo -e "${YELLOW}Starting backend and worker services...${NC}"
docker compose -f $COMPOSE_FILE start backend worker
echo -e "${GREEN}✓ Services started${NC}"
echo ""

# Verify restore
echo -e "${YELLOW}Verifying restore...${NC}"
sleep 5
if docker compose -f $COMPOSE_FILE exec postgres \
    psql -U picur -d picur -c "SELECT COUNT(*) FROM users;" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Database is accessible${NC}"
else
    echo -e "${RED}✗ Database verification failed${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Database restore completed at $(date)${NC}"
echo -e "${BLUE}========================================${NC}"
