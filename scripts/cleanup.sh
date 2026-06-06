#!/bin/bash
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}      $1"; }
warn()    { echo -e "${YELLOW}[AVISO]${NC} $1"; }

REPO_DIR="$HOME/receitas-app"
RUNNER_DIR="$HOME/actions-runner"

echo -e "${YELLOW}  Limpeza da VM                          ${NC}"

warn "Isso vai remover containers, imagens, volumes, Docker e o runner."
warn "Os scripts em $REPO_DIR/scripts/ NÃO serão removidos."
echo ""
read -rp "Tem certeza? (s/N): " CONFIRM
[[ "$CONFIRM" != "s" && "$CONFIRM" != "S" ]] && echo "Cancelado." && exit 0
echo ""

# Self-hosted runner
if [ -f "$RUNNER_DIR/svc.sh" ]; then
  info "Removendo self-hosted runner..."
  cd "$RUNNER_DIR"
  sudo ./svc.sh stop  2>/dev/null || true
  sudo ./svc.sh uninstall 2>/dev/null || true
  ./config.sh remove --unattended 2>/dev/null || true
  cd "$HOME"
  rm -rf "$RUNNER_DIR"
  success "Runner removido."
else
  warn "Runner não encontrado."
fi

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

  info "Removendo redes..."
  docker network prune -f 2>/dev/null || true

  info "Desinstalando Docker..."
  sudo apt purge -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin 2>/dev/null || true
  sudo rm -rf /var/lib/docker /etc/docker
  sudo rm -f /usr/share/keyrings/docker-archive-keyring.gpg
  sudo rm -f /etc/apt/sources.list.d/docker.list
  sudo apt autoremove -y -qq
  success "Docker removido."
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
  rm -rf "$REPO_DIR"
  mkdir -p "$REPO_DIR"
  cp -r "$SCRIPTS_TMP/scripts" "$REPO_DIR/"
  rm -rf "$SCRIPTS_TMP"
  success "Scripts preservados em $REPO_DIR/scripts/"
else
  warn "Repositório não encontrado."
fi

rm -f "$HOME/.env" 2>/dev/null || true

echo ""
echo -e "${GREEN}  Limpeza concluída!                    ${NC}"
echo ""
warn "Bancos removidos junto com os volumes Docker."
warn "Na próxima instalação as migrations recriam tudo configurado."
echo ""