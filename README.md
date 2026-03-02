# 🧠 ClaudIA — Agente de IA Local com Telegram

ClaudIA é um agente de IA que roda 100% localmente na sua VPS usando modelos do Ollama. Ele classifica a intenção de cada mensagem e roteia para o modelo ou skill mais adequado, sem depender de APIs externas com rate limit.

## Como funciona

Cada mensagem que você manda passa por um modelo classificador leve (3B) que decide:

- É uma **pergunta simples**? Responde direto.
- É uma **tarefa** (instalar, executar, criar)? Cria um plano e executa no terminal.
- É **código**? Usa um modelo especializado em código.
- É **imagem**? Encaminha para modelo vision.

## Requisitos

- Ubuntu 20.04+ (VPS ou máquina local)
- 8GB de RAM mínimo
- Python 3.10+
- Conta no Telegram e um bot criado via [@BotFather](https://t.me/BotFather)

## Instalação (um único comando)

```bash
git clone https://github.com/SEU_USUARIO/claudia.git
cd claudia
bash setup.sh
```

O script vai:
1. Instalar o Ollama automaticamente
2. Baixar os modelos necessários (qwen2.5:3b e qwen2.5:7b)
3. Criar o ambiente Python
4. Pedir seu token do Telegram

## Iniciar

```bash
source .venv/bin/activate
python main.py
```

Para rodar automaticamente ao reiniciar o servidor:

```bash
sudo bash install_service.sh
```

## Configuração (config.yml)

Edite o `config.yml` para ajustar:

```yaml
telegram:
  token: "SEU_TOKEN"
  allowed_user_ids: [123456789]  # seu ID do Telegram

models:
  classifier:
    name: qwen2.5:3b   # modelo leve para classificar
  default:
    name: qwen2.5:7b   # modelo principal

skills:
  shell:
    enabled: true      # permite executar comandos no terminal
```

Para descobrir seu ID do Telegram, mande qualquer mensagem para [@userinfobot](https://t.me/userinfobot).

## Comandos disponíveis no Telegram

| Comando | Descrição |
|---------|-----------|
| `/start` | Mensagem de boas-vindas |
| `/status` | Mostra modelo ativo e status |

## Estrutura do projeto

```
claudia/
├── main.py                    # ponto de entrada
├── config.yml                 # sua configuração
├── setup.sh                   # instalação automática
├── install_service.sh         # instala como serviço systemd
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
