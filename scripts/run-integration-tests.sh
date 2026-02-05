#!/bin/bash
# Integration test runner for PicUr
# This script runs end-to-end integration tests

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}PicUr Integration Tests${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if services are running
echo -e "${YELLOW}Checking services...${NC}"
if ! docker-compose -f "$COMPOSE_FILE" ps postgres | grep -q "Up"; then
    echo -e "${RED}Error: PostgreSQL is not running${NC}"
    echo -e "${YELLOW}Start services with: docker-compose up -d${NC}"
    exit 1
fi

if ! docker-compose -f "$COMPOSE_FILE" ps redis | grep -q "Up"; then
    echo -e "${RED}Error: Redis is not running${NC}"
    echo -e "${YELLOW}Start services with: docker-compose up -d${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Services are running${NC}"
echo ""

# Run integration tests
echo -e "${YELLOW}Running integration tests...${NC}"
echo ""

if docker-compose -f "$COMPOSE_FILE" exec -T backend \
    pytest tests/test_integration_e2e.py -v -m integration --tb=short; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}All integration tests passed!${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}Some integration tests failed${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
