# 🧠 ClaudIA — Agente de IA Local com Telegram

ClaudIA é um agente de IA que roda 100% localmente na sua VPS usando modelos do Ollama. Ela classifica a intenção de cada mensagem e roteia para o modelo ou skill mais adequado, sem depender de APIs externas com rate limit.

## Como funciona

Cada mensagem que você manda passa por um modelo classificador leve (0.6B) que decide:

- É uma **pergunta simples**? Responde direto.
- É uma **tarefa** (instalar, executar, criar)? Cria um plano e executa no terminal.
- É **código**? Usa um modelo especializado em código.
- É **imagem**? Encaminha para modelo vision.

## Requisitos

- Docker Engine 24+ e Docker Compose (plugin v2)
- Acesso à internet para baixar as imagens Docker e os modelos Ollama
- Conta no Telegram e um bot criado via [@BotFather](https://t.me/BotFather)

## Instalação (um único comando)

```bash
git clone https://github.com/luan-grabher/claudIA.git
cd claudIA
bash setup.sh
```

O script vai:
1. Validar seu token do bot Telegram via API
2. Validar seu ID de usuário Telegram
3. Criar o `config.yml` automaticamente
4. Configurar swap no host para que os LLMs possam usar disco quando a RAM for insuficiente
5. Subir os containers Docker (Ollama + ClaudIA)
6. Na primeira inicialização, o bot envia uma mensagem de boas-vindas para você no Telegram

## Comandos disponíveis no Telegram

| Comando | Descrição |
|---------|-----------|
| `/start` | Mensagem de boas-vindas |
| `/status` | Mostra modelo ativo e status |
| `/setup` | Mostra a configuração atual do bot |

## Gerenciamento do Docker

```bash
# Ver logs em tempo real
docker compose logs -f claudia

# Ver logs do Ollama
docker compose logs -f ollama

# Parar tudo
docker compose down

# Reiniciar apenas o ClaudIA
docker compose restart claudia

# Reconstruir após mudanças no código
docker compose build && docker compose up -d
```

## Configuração (config.yml)

O `config.yml` é gerado automaticamente pelo `setup.sh`. Você pode editá-lo para ajustar:

```yaml
telegram:
  token: "SEU_TOKEN"
  allowed_user_ids: [123456789]  # seu ID do Telegram

ollama:
  base_url: "http://ollama:11434"  # nome do serviço no docker-compose
  think: true                        # força modo thinking em modelos compatíveis
  think_for_json: false              # mantém respostas JSON estáveis
  log_thinking: false                # true para logar traço de pensamento

models:
  classifier:
    name: qwen3:0.6b   # modelo leve para classificar
  default:
    name: qwen3:4b-thinking   # modelo principal com thinking

skills:
  shell:
    enabled: true      # permite executar comandos no terminal
```

Após editar o `config.yml`, reinicie o ClaudIA:

```bash
docker compose restart claudia
```

## Suporte a disco/SSD para LLMs (baixa memória RAM)

O `setup.sh` configura automaticamente um arquivo de swap de 8 GB no host.  
O Ollama é configurado com `OLLAMA_MAX_LOADED_MODELS=1` para manter apenas um modelo carregado por vez.  
Isso garante que, mesmo com RAM limitada, os modelos funcionarão (mais lentamente, via swap).

## Estrutura do projeto

```
claudIA/
├── main.py                    # ponto de entrada
├── config.example.yml         # template de configuração
├── config.yml                 # sua configuração (gerado pelo setup.sh)
├── requirements.txt           # dependências Python
├── Dockerfile                 # imagem Docker do ClaudIA
├── docker-compose.yml         # orquestração Docker (ClaudIA + Ollama)
├── setup.sh                   # setup interativo (apenas token + user ID)
├── core/
│   ├── classifier.py          # classifica a intenção da mensagem
│   ├── router.py              # roteia para o handler correto
│   └── orchestrator.py        # executa tarefas em múltiplos passos
├── channels/
│   └── telegram_channel.py    # interface com o Telegram
├── models/
│   └── ollama_client.py       # cliente para o Ollama
└── skills/
    ├── base_skill.py          # classe base para skills
    └── shell_skill.py         # skill de terminal
```

## Adicionando skills

Crie um arquivo em `skills/` herdando de `BaseSkill`:

```python
from skills.base_skill import BaseSkill

class MinhaSkill(BaseSkill):
    @property
    def skill_name(self) -> str:
        return "minha_skill"

    @property
    def skill_description(self) -> str:
        return "Descrição do que essa skill faz"

    async def execute(self, instruction: str) -> str:
        # sua lógica aqui
        return "resultado"
```

Depois registre ela no `main.py` dentro da função `build_skills_registry`.

## Licença

MIT
