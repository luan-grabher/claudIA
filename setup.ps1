<#
  setup.ps1 - Script de setup inicial para Windows (PowerShell)
  Versão adaptada do setup.sh para ambientes Windows com Docker Desktop
#>

Set-StrictMode -Version Latest

function Write-Step { param($m) Write-Host "[ClaudIA] $m" -ForegroundColor Green }
function Write-Warn { param($m) Write-Host "[ClaudIA] $m" -ForegroundColor Yellow }
function Write-Err { param($m) Write-Host "[ClaudIA] $m" -ForegroundColor Red }
function Write-Info { param($m) Write-Host "[ClaudIA] $m" -ForegroundColor Cyan }

Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║       ClaudIA — Setup Inicial (Windows)   ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

$configExamplePath = 'config.example.yml'
if (-not (Test-Path -Path $configExamplePath)) {
  Write-Err "Arquivo $configExamplePath não encontrado. Ele é necessário para gerar e atualizar o config.yml."
  exit 1
}

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
$skipCredentials = $false
if (Test-Path -Path 'config.yml') {
  while ($true) {
    $keep = Read-Host -Prompt 'config.yml já existe. Manter configurações existentes? (S/n) [Enter = sim]'
    if ([string]::IsNullOrWhiteSpace($keep) -or $keep -match '^[sS]$') {
      $skipCredentials = $true
      Write-Step "Preservando config.yml existente. Pulando coleta de credenciais."
      break
    }
    elseif ($keep -match '^[nN]$') {
      $skipCredentials = $false
      Write-Step "Você optou por sobrescrever config.yml. Coletando credenciais..."
      break
    }
    else {
      Write-Warn "Resposta inválida. Digite S para manter ou N para sobrescrever (Enter = S)."
    }
  }
}
else {
  Write-Host ""; Write-Info "Você precisará de:"
  Write-Host "  1. Token do bot Telegram (obtenha em @BotFather)"
  Write-Host "  2. Seu ID de usuário Telegram (obtenha em @userinfobot)"; Write-Host ""
}

if (-not $skipCredentials) {
  while ($true) {
    $TELEGRAM_TOKEN = Read-Host -Prompt 'Token do bot Telegram'
    if ([string]::IsNullOrWhiteSpace($TELEGRAM_TOKEN)) {
      Write-Err "Token não pode ser vazio."
      continue
    }

    Write-Step "Validando token do bot..."
    try {
      $response = Invoke-RestMethod -Uri "https://api.telegram.org/bot$TELEGRAM_TOKEN/getMe" -Method Get -TimeoutSec 10 -ErrorAction Stop
    }
    catch {
      $response = $null
    }

    if ($response -and $response.ok) {
      $BOT_NAME = $response.result.username
      Write-Step "✅ Token válido! Bot: @$BOT_NAME"
      break
    }
    else {
      Write-Err "❌ Token inválido ou sem acesso à internet. Tente novamente."
    }
  }

  while ($true) {
    $TELEGRAM_USER_ID = Read-Host -Prompt 'Seu ID de usuário Telegram (somente números)'
    if ($TELEGRAM_USER_ID -match '^[0-9]+$') {
      Write-Step "✅ User ID aceito: $TELEGRAM_USER_ID"
      break
    }
    else {
      Write-Err "ID inválido. Deve conter apenas números (ex: 123456789)."
    }
  }
}
else {
  Write-Step "Preservando config.yml existente."
}

# Configurar swap/pagefile - instruções para Windows
$isAdmin = ([bool](([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)))
if (-not $isAdmin) {
  Write-Warn "Execução não-elevada: não será criado pagefile automaticamente."
  Write-Warn "Para melhor desempenho com LLMs grandes, execute o PowerShell como Administrador e configure o arquivo de paginação (pagefile) nas configurações do sistema."
}
else {
  Write-Info "Executando como Administrador. Se quiser ajustar o pagefile, use as configurações do sistema (System Properties -> Advanced -> Performance -> Settings -> Advanced -> Virtual memory)."
}

# Gerar/atualizar config.yml
if (-not $skipCredentials) {
  Write-Step "Gerando config.yml a partir do config.example.yml..."

  $config = Get-Content -Path $configExamplePath -Raw
  $config = $config -replace '(?m)(^\s*token:\s*)".*"', ('$1"' + $TELEGRAM_TOKEN + '"')
  $config = $config -replace '(?m)(^\s*allowed_user_ids:\s*)\[[^\]]*\]', ('$1[' + $TELEGRAM_USER_ID + ']')

  $config | Out-File -FilePath config.yml -Encoding utf8
  Write-Step "✅ config.yml gerado."
}
else {
  # Atualizar modelos (opcional)
  Write-Host ""
  $updateModels = Read-Host -Prompt 'Deseja atualizar os modelos para os padrões mais recentes? ([Y]/n)'
  if ([string]::IsNullOrWhiteSpace($updateModels) -or $updateModels -match '^[Yy]$') {
    Write-Step "Atualizando configurações iniciais no config.yml com base no config.example.yml..."

    $linhasExample = Get-Content -Path 'config.example.yml'
    $linhasConfig  = Get-Content -Path 'config.yml'
    $secoesSobreescrever = @('ollama:', 'models:', 'orchestrator:')
    $todasSecoes = @('telegram:', 'ollama:', 'models:', 'skills:', 'orchestrator:')

    $blocoAtual = $null
    $blocosDoExample = @{}
    foreach ($linha in $linhasExample) {
      $secaoEncontrada = $todasSecoes | Where-Object { $linha -match "^$_" } | Select-Object -First 1
      if ($secaoEncontrada) {
        $blocoAtual = $secaoEncontrada
        $blocosDoExample[$blocoAtual] = [System.Collections.Generic.List[string]]::new()
        $blocosDoExample[$blocoAtual].Add($linha)
      } elseif ($blocoAtual) {
        $blocosDoExample[$blocoAtual].Add($linha)
      }
    }

    $resultado = [System.Collections.Generic.List[string]]::new()
    $blocoAtual = $null
    $pulandoBloco = $false
    foreach ($linha in $linhasConfig) {
      $secaoEncontrada = $todasSecoes | Where-Object { $linha -match "^$_" } | Select-Object -First 1
      if ($secaoEncontrada) {
        $blocoAtual = $secaoEncontrada
        $pulandoBloco = $secoesSobreescrever -contains $secaoEncontrada
        if ($pulandoBloco -and $blocosDoExample.ContainsKey($secaoEncontrada)) {
          foreach ($l in $blocosDoExample[$secaoEncontrada]) { $resultado.Add($l) }
        }
      }
      if (-not $pulandoBloco) { $resultado.Add($linha) }
    }

    $resultado | Out-File -FilePath 'config.yml' -Encoding utf8
    Write-Step "✅ Configurações iniciais atualizadas a partir do config.example.yml."
  }
  else {
    Write-Step "Configurações iniciais mantidas sem alteração."
  }

  # Adicionar skills ausentes (modo add)
  Write-Step "Verificando skills no config.yml..."

  $linhasExample = Get-Content -Path 'config.example.yml'
  $linhasConfig  = Get-Content -Path 'config.yml'

  $dentroSkillsExample = $false
  $blocosSkillsExample = @{}
  $nomeSkillAtual = $null
  foreach ($linha in $linhasExample) {
    if ($linha -match '^skills:') { $dentroSkillsExample = $true; continue }
    if ($dentroSkillsExample) {
      if ($linha -match '^[a-zA-Z]') { $dentroSkillsExample = $false; continue }
      if ($linha -match '^\s{2}(\w+):') {
        $nomeSkillAtual = $Matches[1]
        $blocosSkillsExample[$nomeSkillAtual] = [System.Collections.Generic.List[string]]::new()
        $blocosSkillsExample[$nomeSkillAtual].Add($linha)
      } elseif ($nomeSkillAtual) {
        $blocosSkillsExample[$nomeSkillAtual].Add($linha)
      }
    }
  }

  $nomesSkillsNoConfig = [System.Collections.Generic.List[string]]::new()
  $dentroSkillsConfig = $false
  foreach ($linha in $linhasConfig) {
    if ($linha -match '^skills:') { $dentroSkillsConfig = $true; continue }
    if ($dentroSkillsConfig) {
      if ($linha -match '^[a-zA-Z]') { $dentroSkillsConfig = $false; continue }
      if ($linha -match '^\s{2}(\w+):') { $nomesSkillsNoConfig.Add($Matches[1]) }
    }
  }

  $skillsParaAdicionar = $blocosSkillsExample.Keys | Where-Object { $_ -notin $nomesSkillsNoConfig }
  if ($skillsParaAdicionar) {
    $resultado = [System.Collections.Generic.List[string]]::new()
    $dentroSkillsConfig = $false
    $indiceInsercao = -1
    $i = 0
    foreach ($linha in $linhasConfig) {
      $resultado.Add($linha)
      if ($linha -match '^skills:') { $dentroSkillsConfig = $true }
      if ($dentroSkillsConfig -and $linha -match '^\s') { $indiceInsercao = $i }
      if ($dentroSkillsConfig -and $linha -match '^[a-zA-Z]' -and $linha -notmatch '^skills:') { $dentroSkillsConfig = $false }
      $i++
    }
    $posicaoInsercao = $indiceInsercao + 1
    foreach ($nomeSkill in $skillsParaAdicionar) {
      $linhasSkill = $blocosSkillsExample[$nomeSkill]
      $offset = 0
      foreach ($l in $linhasSkill) {
        $resultado.Insert($posicaoInsercao + $offset, $l)
        $offset++
      }
      $posicaoInsercao += $offset
    }
    $resultado | Out-File -FilePath 'config.yml' -Encoding utf8
    Write-Step "Skills adicionadas: $($skillsParaAdicionar -join ', ')"
  }
  else {
    Write-Step "Nenhuma nova skill para adicionar."
  }
}

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
}
catch {
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