#!/bin/bash

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_step() { echo -e "${GREEN}[ClaudIA]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[ClaudIA]${NC} $1"; }
print_error() { echo -e "${RED}[ClaudIA]${NC} $1"; }

print_step "=== Configuração do ClaudIA Agent ==="
echo ""

if ! command -v ollama &>/dev/null; then
    print_step "Instalando Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    print_step "Ollama instalado."
else
    print_step "Ollama já está instalado."
fi

if ! systemctl is-active --quiet ollama 2>/dev/null; then
    print_step "Iniciando Ollama..."
    ollama serve &>/dev/null &
    sleep 3
fi

if ! command -v python3 &>/dev/null; then
    print_step "Instalando Python 3..."
    apt-get update -qq && apt-get install -y python3 python3-pip python3-venv
fi

print_step "Criando ambiente virtual Python..."
python3 -m venv .venv
source .venv/bin/activate

print_step "Instalando dependências Python..."
pip install -q -r requirements.txt

if [ ! -f "config.yml" ]; then
    cp config.example.yml config.yml
    print_warn ""
    print_warn "config.yml criado. Você precisa configurar:"
    print_warn ""
    
    echo -e "${YELLOW}Token do bot Telegram (obtenha em @BotFather):${NC}"
    read -r TELEGRAM_TOKEN
    
    if [ -n "$TELEGRAM_TOKEN" ]; then
        sed -i "s/SEU_TOKEN_DO_BOT_AQUI/$TELEGRAM_TOKEN/" config.yml
        print_step "Token configurado."
    else
        print_warn "Token não informado. Edite o config.yml manualmente."
    fi
else
    print_step "config.yml já existe, pulando configuração."
fi

echo ""
print_step "Baixando modelos (isso pode demorar alguns minutos)..."
print_step "Baixando modelo classificador (qwen2.5:3b)..."
ollama pull qwen2.5:3b
print_step "Baixando modelo principal (qwen2.5:7b)..."
ollama pull qwen2.5:7b

echo ""
print_step "=== Instalação concluída! ==="
echo ""
echo -e "Para iniciar o ClaudIA:"
echo -e "  ${GREEN}source .venv/bin/activate${NC}"
echo -e "  ${GREEN}python main.py${NC}"
echo ""
echo -e "Para rodar em background com systemd, execute:"
echo -e "  ${GREEN}sudo bash install_service.sh${NC}"
