<#
  setup.ps1 - Script de setup inicial para Windows (PowerShell)
  Versão adaptada do setup.sh para ambientes Windows com Docker Desktop
#>

Set-StrictMode -Version Latest

function Write-Step { param($m) Write-Host "[ClaudIA] $m" -ForegroundColor Green }
function Write-Warn { param($m) Write-Host "[ClaudIA] $m" -ForegroundColor Yellow }
function Write-Err  { param($m) Write-Host "[ClaudIA] $m" -ForegroundColor Red }
function Write-Info { param($m) Write-Host "[ClaudIA] $m" -ForegroundColor Cyan }

Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║       ClaudIA — Setup Inicial (Windows)   ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

# Verificar dependências
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Err "Docker não está instalado. Instale Docker Desktop: https://docs.docker.com/get-docker/"
    exit 1
}

& docker compose version > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Err "Docker Compose (plugin v2) não está disponível. Ative o Docker Compose v2 ou atualize o Docker Desktop."
    exit 1
}

Write-Step "Dependências mínimas encontradas."

# Coletar credenciais
Write-Host ""; Write-Info "Você precisará de:"
Write-Host "  1. Token do bot Telegram (obtenha em @BotFather)"
Write-Host "  2. Seu ID de usuário Telegram (obtenha em @userinfobot)"; Write-Host ""

while ($true) {
    $TELEGRAM_TOKEN = Read-Host -Prompt 'Token do bot Telegram'
    if ([string]::IsNullOrWhiteSpace($TELEGRAM_TOKEN)) {
        Write-Err "Token não pode ser vazio."
        continue
    }

    Write-Step "Validando token do bot..."
    try {
        $response = Invoke-RestMethod -Uri "https://api.telegram.org/bot$TELEGRAM_TOKEN/getMe" -Method Get -TimeoutSec 10 -ErrorAction Stop
    } catch {
        $response = $null
    }

    if ($response -and $response.ok) {
        $BOT_NAME = $response.result.username
        Write-Step "✅ Token válido! Bot: @$BOT_NAME"
        break
    } else {
        Write-Err "❌ Token inválido ou sem acesso à internet. Tente novamente."
    }
}

while ($true) {
    $TELEGRAM_USER_ID = Read-Host -Prompt 'Seu ID de usuário Telegram (somente números)'
    if ($TELEGRAM_USER_ID -match '^[0-9]+$') {
        Write-Step "✅ User ID aceito: $TELEGRAM_USER_ID"
        break
    } else {
        Write-Err "ID inválido. Deve conter apenas números (ex: 123456789)."
    }
}

# Configurar swap/pagefile - instruções para Windows
$isAdmin = ([bool](([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)))
if (-not $isAdmin) {
    Write-Warn "Execução não-elevada: não será criado pagefile automaticamente."
    Write-Warn "Para melhor desempenho com LLMs grandes, execute o PowerShell como Administrador e configure o arquivo de paginação (pagefile) nas configurações do sistema."
} else {
    Write-Info "Executando como Administrador. Se quiser ajustar o pagefile, use as configurações do sistema (System Properties -> Advanced -> Performance -> Settings -> Advanced -> Virtual memory)."
}

# Gerar config.yml
Write-Step "Gerando config.yml..."

$config = @"
telegram:
  token: """$TELEGRAM_TOKEN"""
  allowed_user_ids: [$TELEGRAM_USER_ID]
  language: "pt-BR"

ollama:
  base_url: "http://ollama:11434"

models:
  classifier:
    name: qwen2.5:3b
  default:
    name: qwen2.5:7b
  code:
    name: qwen2.5-coder:7b
  vision:
    name: llava:7b

skills:
  shell:
    enabled: true
    timeout_seconds: 60

orchestrator:
  max_steps_per_task: 8
  step_timeout_seconds: 120
"@

$config | Out-File -FilePath config.yml -Encoding utf8
Write-Step "✅ config.yml gerado."

# Criar marcador de primeira execução
Write-Step "Marcando como primeira execução..."
New-Item -ItemType Directory -Path claudia_data -Force | Out-Null
New-Item -ItemType File -Path (Join-Path claudia_data '.first_run') -Force | Out-Null

# Iniciar Docker
Write-Step "Construindo e iniciando containers Docker..."
try {
    & docker compose build
    if ($LASTEXITCODE -ne 0) { throw 'Erro ao construir imagens Docker.' }
    & docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw 'Erro ao iniciar containers Docker.' }
} catch {
    Write-Err "Falha ao executar Docker Compose: $_"
    Write-Err "Certifique-se de que o Docker Desktop está em execução e tente novamente."
    exit 1
}

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║  ✅ ClaudIA iniciada com sucesso!                    ║" -ForegroundColor Green
Write-Host "║                                                      ║" -ForegroundColor Green
Write-Host "║  O bot vai enviar uma mensagem de boas-vindas        ║" -ForegroundColor Green
Write-Host "║  para você no Telegram em alguns instantes.          ║" -ForegroundColor Green
Write-Host "║                                                      ║" -ForegroundColor Green
Write-Host "║  Comandos úteis:                                     ║" -ForegroundColor Green
Write-Host "║    docker compose logs -f claudia   # ver logs       ║" -ForegroundColor Green
Write-Host "║    docker compose down              # parar          ║" -ForegroundColor Green
Write-Host "║    docker compose restart claudia   # reiniciar      ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
