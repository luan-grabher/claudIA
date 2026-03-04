#!/bin/bash

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

print_step()  { echo -e "${GREEN}[ClaudIA]${NC} $1"; }
print_warn()  { echo -e "${YELLOW}[ClaudIA]${NC} $1"; }
print_error() { echo -e "${RED}[ClaudIA]${NC} $1"; }
print_info()  { echo -e "${CYAN}[ClaudIA]${NC} $1"; }

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       ClaudIA — Setup Inicial            ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""

CONFIG_EXAMPLE="config.example.yml"
if [ ! -f "$CONFIG_EXAMPLE" ]; then
  print_error "Arquivo $CONFIG_EXAMPLE não encontrado. Ele é necessário para gerar e atualizar o config.yml."
  exit 1
fi

# ─── Verificar dependências ─────────────────────────────────────────────────

if ! command -v docker &>/dev/null; then
    print_error "Docker não está instalado. Instale em: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker compose version &>/dev/null 2>&1; then
    print_error "Docker Compose (plugin v2) não está disponível. Atualize o Docker."
    exit 1
fi

if ! command -v curl &>/dev/null; then
    print_error "curl não está instalado. Instale com: apt install curl"
    exit 1
fi

# ─── Coletar credenciais ─────────────────────────────────────────────────────

SKIP_CREDENTIALS=false
if [ -f "config.yml" ]; then
  echo -e "${YELLOW}config.yml já existe.${NC}"
  while true; do
    echo -n "Deseja manter as configurações existentes? (S/n) [Enter = sim]: "
    read -r KEEP_CONFIG
    if [ -z "$KEEP_CONFIG" ] || [[ "$KEEP_CONFIG" =~ ^[Ss]$ ]]; then
      SKIP_CREDENTIALS=true
      print_step "Preservando config.yml existente. Pulando coleta de credenciais."
      break
    elif [[ "$KEEP_CONFIG" =~ ^[Nn]$ ]]; then
      SKIP_CREDENTIALS=false
      print_step "Você optou por sobrescrever config.yml. Coletando credenciais..."
      break
    else
      print_warn "Resposta inválida. Digite S para manter ou N para sobrescrever."
    fi
  done
else
  echo -e "${CYAN}Você precisará de:${NC}"
  echo "  1. Token do bot Telegram (obtenha em @BotFather)"
  echo "  2. Seu ID de usuário Telegram (obtenha em @userinfobot)"
  echo ""
fi

if [ "$SKIP_CREDENTIALS" != "true" ]; then
  while true; do
    echo -e "${YELLOW}Token do bot Telegram:${NC} "
    read -r TELEGRAM_TOKEN

    if [ -z "$TELEGRAM_TOKEN" ]; then
      print_error "Token não pode ser vazio."
      continue
    fi

    print_step "Validando token do bot..."
    RESPONSE=$(curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getMe" 2>/dev/null || true)

    if echo "$RESPONSE" | grep -q '"ok":true'; then
      BOT_NAME=$(echo "$RESPONSE" | grep -o '"username":"[^"]*"' | cut -d'"' -f4)
      print_step "✅ Token válido! Bot: @${BOT_NAME}"
      break
    else
      print_error "❌ Token inválido ou sem acesso à internet. Tente novamente."
    fi
  done

  echo ""
  while true; do
    echo -e "${YELLOW}Seu ID de usuário Telegram (somente números):${NC} "
    read -r TELEGRAM_USER_ID

    if [[ ! "$TELEGRAM_USER_ID" =~ ^[0-9]+$ ]]; then
      print_error "ID inválido. Deve conter apenas números (ex: 123456789)."
      continue
    fi

    print_step "✅ User ID aceito: ${TELEGRAM_USER_ID}"
    break
  done
fi

# ─── Configurar swap (para suporte de LLM em disco quando RAM for insuficiente) ─

SWAP_FILE="/swapfile"
SWAP_SIZE_MB=8192  # 8 GB de swap

if [ "$(id -u)" -ne 0 ]; then
    print_warn "Swap não configurado (execução não-root)."
    print_warn "Para melhor desempenho com LLMs grandes, execute como root ou configure swap manualmente:"
    print_warn "  sudo fallocate -l 8G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile"
elif [ -f "$SWAP_FILE" ]; then
    print_info "Swap já configurado, pulando."
else
    print_step "Configurando swap de ${SWAP_SIZE_MB}MB para suporte de LLM em disco..."
    fallocate -l "${SWAP_SIZE_MB}M" "$SWAP_FILE" 2>/dev/null \
        || dd if=/dev/zero of="$SWAP_FILE" bs=1M count="$SWAP_SIZE_MB" status=none
    chmod 600 "$SWAP_FILE"
    mkswap "$SWAP_FILE"
    swapon "$SWAP_FILE"
    echo "$SWAP_FILE none swap sw 0 0" >> /etc/fstab
    print_step "✅ Swap configurado (${SWAP_SIZE_MB}MB)."
fi

# ─── Gerar/atualizar config.yml ──────────────────────────────────────────────

if [ "$SKIP_CREDENTIALS" != "true" ]; then
  print_step "Gerando config.yml a partir do config.example.yml..."

  sed -E \
    -e "s|^([[:space:]]*token:[[:space:]]*).*$|\\1\"${TELEGRAM_TOKEN}\"|" \
    -e "s|^([[:space:]]*allowed_user_ids:[[:space:]]*)\[[^]]*\](.*)$|\\1[${TELEGRAM_USER_ID}]\\2|" \
    "$CONFIG_EXAMPLE" > config.yml

    print_step "✅ config.yml gerado."
else
  PYTHON_CMD=""
  if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
  elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
  fi

    # ─── Atualizar modelos (opcional) ─────────────────────────────────────────
    echo ""
    echo -n "Deseja atualizar os modelos para os padrões mais recentes? ([Y]/n): "
    read -r UPDATE_MODELS
    if [ -z "$UPDATE_MODELS" ] || [[ "$UPDATE_MODELS" =~ ^[Yy]$ ]]; then
    print_step "Atualizando configurações iniciais no config.yml com base no config.example.yml..."
    if [ -n "$PYTHON_CMD" ]; then
    "$PYTHON_CMD" - <<'PYEOF'
import yaml
with open('config.example.yml', 'r') as f:
  template = yaml.safe_load(f) or {}
with open('config.yml', 'r') as f:
  config = yaml.safe_load(f) or {}
for section in ('ollama', 'models', 'orchestrator'):
  if section in template:
    config[section] = template[section]
with open('config.yml', 'w') as f:
    yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
PYEOF
    print_step "✅ Configurações iniciais atualizadas a partir do config.example.yml."
    else
      print_warn "Python não encontrado. Atualize manualmente as configurações iniciais no config.yml com base no config.example.yml."
    fi
    else
    print_step "Configurações iniciais mantidas sem alteração."
    fi

    # ─── Adicionar skills ausentes (modo add) ─────────────────────────────────
    print_step "Verificando skills no config.yml..."
  if [ -n "$PYTHON_CMD" ]; then
  "$PYTHON_CMD" - <<'PYEOF'
import yaml
with open('config.example.yml', 'r') as f:
  template = yaml.safe_load(f) or {}
default_skills = template.get('skills') or {}
with open('config.yml', 'r') as f:
  config = yaml.safe_load(f) or {}
if 'skills' not in config:
    config['skills'] = {}
added = []
for skill, defaults in default_skills.items():
    if skill not in config['skills']:
        config['skills'][skill] = defaults
        added.append(skill)
if added:
    with open('config.yml', 'w') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"Skills adicionadas: {', '.join(added)}")
else:
    print("Nenhuma nova skill para adicionar.")
PYEOF
  else
    print_warn "Python não encontrado. Verifique manualmente se todas as skills estão no config.yml com base no config.example.yml."
  fi
fi

# ─── Criar marcador de primeira execução ─────────────────────────────────────

print_step "Marcando como primeira execução..."
mkdir -p claudia_data
touch claudia_data/.first_run

# ─── Iniciar Docker ───────────────────────────────────────────────────────────

print_step "Construindo e iniciando containers Docker..."
docker compose build
docker compose up -d

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✅ ClaudIA iniciada com sucesso!                    ║${NC}"
echo -e "${GREEN}║                                                      ║${NC}"
echo -e "${GREEN}║  O bot vai enviar uma mensagem de boas-vindas        ║${NC}"
echo -e "${GREEN}║  para você no Telegram em alguns instantes.          ║${NC}"
echo -e "${GREEN}║                                                      ║${NC}"
echo -e "${GREEN}║  Comandos úteis:                                     ║${NC}"
echo -e "${GREEN}║    docker compose logs -f claudia   # ver logs       ║${NC}"
echo -e "${GREEN}║    docker compose down              # parar          ║${NC}"
echo -e "${GREEN}║    docker compose restart claudia  # reiniciar       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
