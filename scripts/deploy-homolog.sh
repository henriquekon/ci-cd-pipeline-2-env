#!/bin/bash
set -e

GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }

ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME=$(getent passwd "$ACTUAL_USER" | cut -d: -f6)
REPO_DIR="$ACTUAL_HOME/receitas-app"
COMPOSE_FILE="$REPO_DIR/infra/homolog/docker-compose.yml"
ENV_FILE="$REPO_DIR/.env"

info "Atualizando repositório..."
git -C "$REPO_DIR" pull --ff-only

info "Atualizando stack de homologação..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" \
  up --pull always --remove-orphans -d

success "Homologação atualizada → http://localhost:8081"