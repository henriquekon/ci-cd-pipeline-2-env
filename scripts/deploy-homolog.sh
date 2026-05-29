#!/bin/bash
set -e

GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }

REPO_DIR="$HOME/receitas-app"
COMPOSE_FILE="$REPO_DIR/infra/homolog/docker-compose.yml"
ENV_FILE="$REPO_DIR/.env"
IMAGE="ghcr.io/henriquekon/ci-cd-pipeline-2-env:latest"

info "Puxando imagem mais recente..."
docker pull "$IMAGE"

info "Derrubando stack de homologação..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down --remove-orphans

info "Subindo stack de homologação (migrations rodam automaticamente)..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

success "Homologação atualizada na porta 8081"