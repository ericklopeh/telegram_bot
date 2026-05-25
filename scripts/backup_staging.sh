#!/usr/bin/env bash
# P77 — backup PostgreSQL staging (wrapper)
export COMPOSE_FILE=docker-compose.staging.yml
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${SCRIPT_DIR}/backup_db.sh"
