from typing import Callable, Awaitable
from models.ollama_client import OllamaClient
from core.classifier import IntentClassifier
from core.orchestrator import TaskOrchestrator

GENERAL_ASSISTANT_SYSTEM_PROMPT = """Você é ClaudIA, uma assistente de IA pessoal que roda localmente.
Seu nome vem de "Claudia", um nome brasileiro comum, e "IA" de Inteligência Artificial.
Você é próxima, prestativa e direta — como uma funcionária de confiança.
Responda sempre em português brasileiro de forma clara e objetiva.
Você tem acesso ao terminal Linux do servidor onde está rodando.
Skills disponíveis: {skills}
Ao falar sobre suas capacidades, mencione apenas as skills listadas acima."""

CODE_ASSISTANT_SYSTEM_PROMPT = """Você é ClaudIA, assistente pessoal especializada em código.
Analise, escreva ou corrija código conforme pedido.
Responda em português com explicações claras e objetivas."""

MAX_HISTORY_MESSAGES = 20

DESCRICAO_LEGIVEL_POR_TIPO_DE_INTENCAO = {
    "pergunta": "uma pergunta",
    "tarefa": "uma tarefa para executar",
    "busca": "uma busca na internet",
    "codigo": "uma solicitação de código",
    "imagem": "algo sobre uma imagem",
    "conversa": "uma conversa",
    "ambigua": "uma mensagem que precisa de esclarecimento",
}

ProgressCallback = Callable[[str], Awaitable[None]]


class IntentRouter:
    def __init__(
        self,
        ollama_client: OllamaClient,
        classifier: IntentClassifier,
        orchestrator: TaskOrchestrator,
        skills_registry: dict,
        config: dict,
    ):
        self.ollama_client = ollama_client
        self.classifier = classifier
        self.orchestrator = orchestrator
        self.skills_registry = skills_registry
        self.config = config
        self.default_model_name = config["models"]["default"]["name"]
        self.code_model_name = config["models"].get("code", {}).get("name", self.default_model_name)
        self.log_thinking_habilitado = config.get("ollama", {}).get("log_thinking", False)
        self._conversation_histories: dict = {}

    def _get_skills_description(self) -> str:
        if not self.skills_registry:
            return "nenhuma skill ativa"
        return ", ".join(self.skills_registry.keys())

    def _get_history(self, user_id: int) -> list:
        return self._conversation_histories.get(user_id, [])

    def _add_to_history(self, user_id: int, user_message: str, assistant_response: str):
        if user_id not in self._conversation_histories:
            self._conversation_histories[user_id] = []
        history = self._conversation_histories[user_id]
        if len(history) >= MAX_HISTORY_MESSAGES:
            self._conversation_histories[user_id] = history[-(MAX_HISTORY_MESSAGES - 2):]
            history = self._conversation_histories[user_id]
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": assistant_response})

    def _logar_pensamento_se_habilitado(self, pensamento: str | None, contexto: str):
        if self.log_thinking_habilitado and pensamento:
            print(f"[THINKING:{contexto}] {pensamento}")

    async def _notificar_progresso_se_possivel(self, callback: ProgressCallback | None, mensagem: str):
        if callback:
            await callback(mensagem)

    async def route_and_handle_message(
        self,
        user_message: str,
        has_image: bool = False,
        user_id: int = 0,
        progress_callback: ProgressCallback = None,
    ) -> str:
        await self._notificar_progresso_se_possivel(progress_callback, "✍️ Mensagem recebida, estou pensando...")

        if has_image:
            await self._notificar_progresso_se_possivel(progress_callback, "🖼️ Entendi que sua solicitação é sobre uma imagem, processando...")
            response = await self._handle_image_message(user_message)
            self._add_to_history(user_id, user_message, response)
            return response

        classification = await self.classifier.classify_user_message(user_message)
        intent_type = classification["tipo"]
        print(f"[Router] Tipo: {intent_type} | Skill: {classification.get('skill_sugerida')} | Resumo: {classification.get('resumo_intencao')}")

        descricao_legivel = DESCRICAO_LEGIVEL_POR_TIPO_DE_INTENCAO.get(intent_type, intent_type)
        await self._notificar_progresso_se_possivel(progress_callback, f"🧠 Entendi que sua solicitação é {descricao_legivel}.")

        history = self._get_history(user_id)

        if intent_type == "ambigua":
            clarification = classification.get("pergunta_esclarecimento") or "Poderia ser mais específico sobre o que você precisa?"
            if not classification.get("pergunta_esclarecimento"):
                print(f"[Router] AVISO: classificador retornou 'ambigua' sem pergunta_esclarecimento. Usando fallback.")
            print(f"[Router] Mensagem ambígua. Solicitando esclarecimento.")
            self._add_to_history(user_id, user_message, clarification)
            return clarification

        if intent_type == "tarefa":
            skill_sugerida = classification.get("skill_sugerida")
            mensagem_skill = f" Vou usar a skill `{skill_sugerida}`." if skill_sugerida else ""
            await self._notificar_progresso_se_possivel(progress_callback, f"⚙️ Iniciando execução da tarefa...{mensagem_skill}")
            response = await self._handle_task(user_message, classification, history)
        elif intent_type == "busca":
            await self._notificar_progresso_se_possivel(progress_callback, "🔍 Buscando na internet, aguarde...")
            response = await self._handle_task(user_message, classification, history)
        elif intent_type == "codigo":
            await self._notificar_progresso_se_possivel(progress_callback, "💻 Analisando o código, aguarde...")
            response = await self._handle_code_request(user_message)
        elif intent_type == "imagem":
            await self._notificar_progresso_se_possivel(progress_callback, "🖼️ Processando a imagem...")
            response = await self._handle_image_message(user_message)
        else:
            response = await self._handle_general_conversation(user_message, user_id)

        self._add_to_history(user_id, user_message, response)
        return response

    async def _handle_task(self, user_message: str, classification: dict, conversation_history: list) -> str:
        suggested_skill = classification.get("skill_sugerida")
        if suggested_skill and suggested_skill not in self.skills_registry:
            suggested_skill = None
        return await self.orchestrator.execute_task_with_planning(
            task_description=user_message,
            suggested_skill=suggested_skill,
            recent_conversation_history=conversation_history,
        )

    async def _handle_code_request(self, user_message: str) -> str:
        resposta_bruta = await self.ollama_client.generate_completion(
            prompt=user_message,
            model_name=self.code_model_name,
            system_prompt=CODE_ASSISTANT_SYSTEM_PROMPT,
        )
        self._logar_pensamento_se_habilitado(resposta_bruta.get("thinking"), "codigo")
        return resposta_bruta["content"]

    async def _handle_general_conversation(self, user_message: str, user_id: int) -> str:
        system_prompt = GENERAL_ASSISTANT_SYSTEM_PROMPT.format(skills=self._get_skills_description())
        history = self._get_history(user_id)
        messages = history + [{"role": "user", "content": user_message}]
        resposta_bruta = await self.ollama_client.generate_chat_completion(
            messages=messages,
            model_name=self.default_model_name,
            system_prompt=system_prompt,
        )
        self._logar_pensamento_se_habilitado(resposta_bruta.get("thinking"), "conversa")
        return resposta_bruta["content"]

    async def _handle_image_message(self, user_message: str) -> str:
        vision_model = self.config["models"].get("vision", {}).get("name")
        if not vision_model:
            return "Não há modelo de visão configurado. Adicione um modelo vision no config.yml."
        system_prompt = GENERAL_ASSISTANT_SYSTEM_PROMPT.format(skills=self._get_skills_description())
        resposta_bruta = await self.ollama_client.generate_completion(
            prompt=user_message,
            model_name=vision_model,
            system_prompt=system_prompt,
            forcar_desativar_think=True,
        )
        return resposta_bruta["content"]