import asyncio
import yaml
import sys
from models.ollama_client import OllamaClient
from core.classifier import IntentClassifier
from core.orchestrator import TaskOrchestrator
from core.router import IntentRouter
from channels.telegram_channel import TelegramChannel
from skills.shell_skill import ShellSkill


def load_config_from_yaml_file() -> dict:
    try:
        with open("config.yml", "r", encoding="utf-8") as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        print("[ClaudIA] ERRO: config.yml não encontrado.")
        print("[ClaudIA] Copie o config.example.yml para config.yml e configure.")
        sys.exit(1)


def build_skills_registry(config: dict) -> dict:
    registry = {}
    skills_config = config.get("skills", {})

    if skills_config.get("shell", {}).get("enabled", False):
        registry["shell"] = ShellSkill(config)
        print("[ClaudIA] Skill 'shell' carregada.")

    return registry


async def pull_required_models(ollama_client: OllamaClient, config: dict):
    models_to_ensure = [
        config["models"]["classifier"]["name"],
        config["models"]["default"]["name"],
    ]

    for model_name in models_to_ensure:
        await ollama_client.pull_model_if_not_available(model_name)


async def start_claudia():
    print("[ClaudIA] Iniciando...")
    config = load_config_from_yaml_file()

    ollama_client = OllamaClient(base_url=config["ollama"]["base_url"])

    print("[ClaudIA] Verificando modelos necessários no Ollama...")
    await pull_required_models(ollama_client, config)

    skills_registry = build_skills_registry(config)

    classifier = IntentClassifier(
        ollama_client=ollama_client,
        classifier_model_name=config["models"]["classifier"]["name"],
    )

    orchestrator = TaskOrchestrator(
        ollama_client=ollama_client,
        skills_registry=skills_registry,
        config=config,
    )

    router = IntentRouter(
        ollama_client=ollama_client,
        classifier=classifier,
        orchestrator=orchestrator,
        skills_registry=skills_registry,
        config=config,
    )

    telegram_channel = TelegramChannel(router=router, config=config)

    print("[ClaudIA] Tudo pronto!")
    await telegram_channel.start()


if __name__ == "__main__":
    asyncio.run(start_claudia())
