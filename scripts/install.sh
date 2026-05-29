#!/bin/bash
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}      $1"; }
warn()    { echo -e "${YELLOW}[AVISO]${NC} $1"; }
error()   { echo -e "${RED}[ERRO]${NC}   $1"; exit 1; }

REPO_URL="https://github.com/henriquekon/ci-cd-pipeline-2-env.git"
REPO_DIR="$HOME/receitas-app"

echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}  Instalador – Sistema de Receitas      ${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Senhas dos bancos
info "Configuração dos bancos de dados (locais em container)"
echo ""
read -rsp "Senha do banco de HOMOLOGAÇÃO: " DB_PASSWORD_HOMOLOG
echo ""
read -rsp "Senha do banco de PRODUÇÃO: " DB_PASSWORD_PROD
echo ""

[[ -z "$DB_PASSWORD_HOMOLOG" || -z "$DB_PASSWORD_PROD" ]] && \
  error "As senhas dos bancos são obrigatórias."
success "Senhas salvas."
echo ""

# E-mail
info "Configuração de e-mail para notificações"
echo ""
read -rp "Host SMTP (padrão: smtp.gmail.com): " MAIL_HOST
MAIL_HOST=${MAIL_HOST:-smtp.gmail.com}
read -rp "Porta SMTP (padrão: 587): " MAIL_PORT
MAIL_PORT=${MAIL_PORT:-587}
read -rp "Usuário SMTP: " MAIL_USER
read -rsp "Senha SMTP: " MAIL_PASS
echo ""
read -rp "E-mail remetente (ex: app@gmail.com): " MAIL_FROM
read -rp "E-mail destinatário (quem recebe alertas): " MAIL_TO

[[ -z "$MAIL_USER" || -z "$MAIL_PASS" || -z "$MAIL_FROM" || -z "$MAIL_TO" ]] && \
  error "Todos os campos de e-mail são obrigatórios."
success "Configuração de e-mail salva."
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
  sudo usermod -aG docker "$USER"
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
MAIL_TO=${MAIL_TO}

DB_PASSWORD_HOMOLOG=${DB_PASSWORD_HOMOLOG}
DB_PASSWORD_PROD=${DB_PASSWORD_PROD}
EOF
success ".env criado."
echo ""

# Login no ghcr.io (para baixar a imagem privada, se necessário)
info "Login no GitHub Container Registry..."
read -rp "GitHub username: " GH_USER
read -rsp "GitHub token (com permissão read:packages): " GH_TOKEN
echo ""
echo "$GH_TOKEN" | docker login ghcr.io -u "$GH_USER" --password-stdin
success "Login no ghcr.io realizado."
echo ""

# Sobe ambientes
info "Subindo ambiente de HOMOLOGAÇÃO..."
bash "$REPO_DIR/scripts/deploy-homolog.sh"

info "Subindo ambiente de PRODUÇÃO..."
bash "$REPO_DIR/scripts/deploy-prod.sh"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Instalação concluída!                 ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  Produção:     ${BLUE}http://localhost:8080${NC}"
echo -e "  Homologação:  ${BLUE}http://localhost:8081${NC}"
echo ""
echo -e "  Login:        admin / admin123"
echo -e "  Notificações: ${MAIL_TO}"
echo ""