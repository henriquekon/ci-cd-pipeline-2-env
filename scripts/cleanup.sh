#!/bin/bash
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}      $1"; }
warn()    { echo -e "${YELLOW}[AVISO]${NC} $1"; }

REPO_DIR="$HOME/receitas-app"

echo -e "\n${YELLOW}========================================${NC}"
echo -e "${YELLOW}  Limpeza – VM                          ${NC}"
echo -e "${YELLOW}========================================${NC}\n"

warn "Isso vai remover containers, imagens, volumes e o repositório."
warn "Os scripts em ~/receitas-app/scripts/ NÃO serão removidos."
echo ""
read -rp "Tem certeza? (s/N): " CONFIRM
[[ "$CONFIRM" != "s" && "$CONFIRM" != "S" ]] && echo "Cancelado." && exit 0
echo ""

# Stacks Docker
if command -v docker &>/dev/null; then
  info "Derrubando stack de homologação..."
  docker compose \
    -f "$REPO_DIR/infra/homolog/docker-compose.yml" \
    --env-file "$REPO_DIR/.env" \
    down --volumes 2>/dev/null || true

  info "Derrubando stack de produção..."
  docker compose \
    -f "$REPO_DIR/infra/prod/docker-compose.yml" \
    --env-file "$REPO_DIR/.env" \
    down --volumes 2>/dev/null || true

  info "Removendo containers restantes..."
  docker ps -aq | xargs -r docker rm -f 2>/dev/null || true

  info "Removendo imagens..."
  docker images -q | xargs -r docker rmi -f 2>/dev/null || true

  info "Removendo volumes órfãos..."
  docker volume ls -q | xargs -r docker volume rm 2>/dev/null || true

  info "Removendo redes criadas..."
  docker network prune -f 2>/dev/null || true

  success "Docker limpo."
else
  warn "Docker não estava instalado."
fi

# Firewall
info "Removendo regras de firewall..."
sudo ufw delete allow 8080/tcp 2>/dev/null || true
sudo ufw delete allow 8081/tcp 2>/dev/null || true
success "Regras removidas."

# Repositório — preserva scripts/
if [ -d "$REPO_DIR" ]; then
  info "Preservando scripts..."
  SCRIPTS_TMP="$(mktemp -d)"
  cp -r "$REPO_DIR/scripts" "$SCRIPTS_TMP/"

  info "Removendo repositório..."
  rm -rf "$REPO_DIR"

  info "Restaurando scripts..."
  mkdir -p "$REPO_DIR"
  cp -r "$SCRIPTS_TMP/scripts" "$REPO_DIR/"
  rm -rf "$SCRIPTS_TMP"

  success "Repositório removido. Scripts preservados em $REPO_DIR/scripts/"
else
  warn "Repositório não encontrado."
fi

# .env
rm -f "$HOME/.env" 2>/dev/null || true

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Limpeza concluída!                    ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
warn "Os bancos de dados foram removidos junto com os volumes Docker."
warn "Na próxima instalação as migrations recriam tudo automaticamente."
echo ""