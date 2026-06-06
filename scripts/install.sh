#!/bin/bash
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[AVISO]${NC} $1"; }
error() { echo -e "${RED}[ERRO]${NC} $1"; exit 1; }

REPO_URL="https://github.com/henriquekon/ci-cd-pipeline-2-env.git"

# valores padrão (EDITAR ANTES DE RODAR)
GH_USER="henriquekon"
GH_REPO="ci-cd-pipeline-2-env"
GH_TOKEN="" # PREENCHER: token com read:packages e repo (para o runner)
MAIL_HOST="sandbox.smtp.mailtrap.io"
MAIL_PORT="587"
MAIL_USER="" # PREENCHER: usuário SMTP Mailtrap
MAIL_PASS="" # PREENCHER: senha SMTP Mailtrap
MAIL_FROM="receitas@app.com"
ADMIN_EMAIL="" # PREENCHER: email do admin

# Detecta usuário real (quem rodou sudo)
ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME=$(getent passwd "$ACTUAL_USER" | cut -d: -f6)
REPO_DIR="$ACTUAL_HOME/receitas-app"
RUNNER_DIR="$ACTUAL_HOME/actions-runner"
# ----------------------------------------

echo -e "${BLUE}Instalador Sistema de Receitas ${NC}"

# Senhas dos bancos
info "Configuração dos bancos de dados"
echo ""
read -rsp "Senha do banco de HOMOLOGAÇÃO: " DB_PASSWORD_HOMOLOG; echo ""
read -rsp "Senha do banco de PRODUÇÃO: " DB_PASSWORD_PROD; echo ""
[[ -z "$DB_PASSWORD_HOMOLOG" || -z "$DB_PASSWORD_PROD" ]] && error "Senhas obrigatórias."
success "Senhas salvas."
echo ""

# Credenciais interativas
[[ -z "$GH_TOKEN" ]] && { read -rsp "GitHub token (read:packages + repo): " GH_TOKEN; echo ""; }
[[ -z "$MAIL_USER" ]] && { read -rp "Usuário SMTP Mailtrap: " MAIL_USER; }
[[ -z "$MAIL_PASS" ]] && { read -rsp "Senha SMTP Mailtrap: " MAIL_PASS; echo ""; }
[[ -z "$ADMIN_EMAIL" ]] && { read -rp "E-mail do admin (notificações): " ADMIN_EMAIL; }

[[ -z "$GH_TOKEN" || -z "$MAIL_USER" || -z "$MAIL_PASS" || -z "$ADMIN_EMAIL" ]] && \
  error "Credenciais incompletas."
success "Configurações prontas."
echo ""

# Docker
if ! command -v docker &>/dev/null; then
  info "Instalando Docker..."
  sudo apt update -qq
  sudo apt install -y -qq apt-transport-https ca-certificates curl software-properties-common git
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
    https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt update -qq
  sudo apt install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
  sudo systemctl start docker
  sudo systemctl enable docker
  sudo usermod -aG docker "$ACTUAL_USER"
  success "Docker instalado."
else
  success "Docker já instalado."
fi

# Firewall
info "Configurando firewall..."
sudo ufw allow 8080/tcp
sudo ufw allow 8081/tcp
success "Portas 8080 e 8081 liberadas."
echo ""

# Repositório
if [ -d "$REPO_DIR/.git" ]; then
  info "Repositório já existe – atualizando..."
  git -C "$REPO_DIR" pull --ff-only
else
  info "Clonando repositório..."
  rm -rf "$REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
fi
success "Repositório pronto em $REPO_DIR"
echo ""

# .env
cat > "$REPO_DIR/.env" <<EOF
MAIL_HOST=${MAIL_HOST}
MAIL_PORT=${MAIL_PORT}
MAIL_USER=${MAIL_USER}
MAIL_PASS=${MAIL_PASS}
MAIL_FROM=${MAIL_FROM}

DB_PASSWORD_HOMOLOG=${DB_PASSWORD_HOMOLOG}
DB_PASSWORD_PROD=${DB_PASSWORD_PROD}

ADMIN_EMAIL=${ADMIN_EMAIL}
EOF
success ".env criado."
echo ""

# Login ghcr.io
info "Login no GitHub Container Registry..."
echo "$GH_TOKEN" | docker login ghcr.io -u "$GH_USER" --password-stdin
success "Login no ghcr.io realizado."
echo ""

# Self-hosted runner
info "Configurando GitHub Actions self-hosted runner..."

RUNNER_RESPONSE=$(curl -s -X POST \
  -H "Authorization: token ${GH_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GH_USER}/${GH_REPO}/actions/runners/registration-token")

RUNNER_TOKEN=$(echo "$RUNNER_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
[[ -z "$RUNNER_TOKEN" ]] && error "Não foi possível obter token do runner."

RUNNER_VERSION="2.322.0"
sudo -u "$ACTUAL_USER" mkdir -p "$RUNNER_DIR"

if [ ! -f "$RUNNER_DIR/run.sh" ]; then
  info "Baixando runner..."
  curl -sL "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz" \
    | sudo -u "$ACTUAL_USER" tar xz -C "$RUNNER_DIR"
fi

info "Configurando runner..."
sudo -u "$ACTUAL_USER" bash -c "
  cd '$RUNNER_DIR'
  ./config.sh \
    --url 'https://github.com/${GH_USER}/${GH_REPO}' \
    --token '$RUNNER_TOKEN' \
    --name 'vm-univates' \
    --labels 'self-hosted,linux' \
    --unattended \
    --replace
"

info "Instalando serviço..."
cd "$RUNNER_DIR"
sudo ./svc.sh install "$ACTUAL_USER"
sudo ./svc.sh start
cd "$ACTUAL_HOME"
success "Runner instalado e rodando."
echo ""

# Sobe ambientes
info "Subindo HOMOLOGAÇÃO..."
bash "$REPO_DIR/scripts/deploy-homolog.sh"

info "Subindo PRODUÇÃO..."
bash "$REPO_DIR/scripts/deploy-prod.sh"

echo -e "${GREEN}Instalação concluída! ${NC}"
echo -e "Produção: ${BLUE}http://localhost:8080${NC}"
echo -e "Homologação: ${BLUE}http://localhost:8081${NC}"
echo -e "Login: admin / admin123"