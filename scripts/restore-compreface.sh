#!/bin/bash
# CompreFace database restore script.
#
# Restores the `frs` database from a custom-format pg_dump produced by
# `backup-compreface.sh`. After this completes you MUST restart the
# compreface-api and compreface-admin containers so they pick up the
# restored state.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml -f docker-compose.vps.yml}"

if [ -z "$1" ]; then
    echo -e "${RED}Error: Backup file not specified${NC}"
    echo -e "${YELLOW}Usage: $0 <frs_backup_*.dump>${NC}"
    echo ""
    echo -e "${YELLOW}Available backups:${NC}"
    ls -lh /backups/compreface/*.dump 2>/dev/null || echo "No backups found"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}Error: Backup file not found: $BACKUP_FILE${NC}"
    exit 1
fi

case "$BACKUP_FILE" in
    *.dump) : ;;
    *)
        echo -e "${RED}Error: Expect a .dump (pg_dump -Fc) file${NC}"
        exit 1
        ;;
esac

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}PicUr CompreFace Restore${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Backup file: $BACKUP_FILE${NC}"
echo -e "${YELLOW}Backup size: $(du -h "$BACKUP_FILE" | cut -f1)${NC}"
echo ""

echo -e "${RED}WARNING: This will overwrite the CompreFace face-recognition state!${NC}"
echo -e "${RED}All current face indexes will be replaced.${NC}"
read -p "Are you sure you want to continue? (yes/no): " -r
echo
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo -e "${YELLOW}Restore cancelled${NC}"
    exit 0
fi

echo -e "${YELLOW}Stopping CompreFace API + admin...${NC}"
docker compose -f $COMPOSE_FILE stop compreface-api compreface-admin
echo -e "${GREEN}✓ CompreFace stopped${NC}"

echo -e "${YELLOW}Restoring frs database...${NC}"
if docker compose -f $COMPOSE_FILE exec -T compreface-postgres-db \
    pg_restore --clean --if-exists --no-owner --no-privileges \
               -U postgres -d frs < "$BACKUP_FILE"; then
    echo -e "${GREEN}✓ Database restored${NC}"
else
    echo -e "${RED}✗ Database restore failed${NC}"
    docker compose -f $COMPOSE_FILE start compreface-api compreface-admin
    exit 1
fi

echo -e "${YELLOW}Restarting CompreFace services...${NC}"
docker compose -f $COMPOSE_FILE start compreface-api compreface-admin
echo -e "${GREEN}✓ CompreFace started${NC}"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}CompreFace restore completed at $(date)${NC}"
echo -e "${BLUE}========================================${NC}"
