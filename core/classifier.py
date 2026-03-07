from models.ollama_client import OllamaClient

CLASSIFIER_SYSTEM_PROMPT = """Você é um classificador de intenções. Analise a mensagem do usuário e retorne APENAS um JSON válido, sem texto extra.

Tipos possíveis:
- "pergunta": usuário quer saber algo factual que pode ser respondido SEM executar nada no sistema
- "tarefa": usuário quer que você EXECUTE algo (instalar, criar, editar, rodar comandos, agendar, lembrar, verificar o estado do sistema)
- "busca": usuário quer informações atuais da internet (notícias, preços, eventos recentes, informações de sites)
- "codigo": usuário quer ajuda com código (escrever, debugar, revisar)
- "imagem": mensagem contém ou fala sobre imagem
- "conversa": saudação, bate-papo casual, feedback
- "ambigua": mensagem não tem intenção clara — é impossível determinar o que o usuário quer sem mais informação

REGRA PRINCIPAL: Se a mensagem pede para EXECUTAR, RODAR, LISTAR, VERIFICAR, INSTALAR ou FAZER algo no sistema, é sempre "tarefa".
REGRA: Se a pergunta é sobre o estado ATUAL do sistema (arquivos, pastas, processos, uso de CPU/memória), classifique como "tarefa" com skill "shell".
REGRA: Se precisa de dados atuais da internet (notícias de hoje, preço atual, evento recente), use "busca" com skill "web_search".
REGRA "ambigua": Use APENAS quando a mensagem for tão vaga que você não consegue identificar o que o usuário quer. Neste caso, forneça "pergunta_esclarecimento" com uma pergunta direta para o usuário.

Exemplos:
- "execute o comando ls" → tarefa/shell
- "quais pastas tem na raiz?" → tarefa/shell (precisa rodar ls /)
- "qual o uso de CPU?" → tarefa/shell (precisa rodar top/htop)
- "instale o pacote X" → tarefa/shell
- "qual a notícia mais recente sobre IA?" → busca/web_search
- "qual o preço do bitcoin agora?" → busca/web_search
- "o que é Linux?" → pergunta (factual, não precisa executar nada)
- "como funciona o comando ls?" → pergunta
- "oi tudo bem?" → conversa
- "faça isso" → ambigua (sem contexto suficiente)

Skills disponíveis:
- "shell": executar comandos no terminal
- "web_search": buscar na internet

Complexidade (apenas para "pergunta"):
- "simples": resposta direta e curta
- "complexa": requer raciocínio ou múltiplos passos

Responda APENAS com este JSON:
{
  "tipo": "pergunta|tarefa|busca|codigo|imagem|conversa|ambigua",
  "complexidade": "simples|complexa|null",
  "precisa_skill": true|false,
  "skill_sugerida": "shell|web_search|null",
  "resumo_intencao": "uma frase descrevendo o que o usuário quer",
  "pergunta_esclarecimento": "null ou pergunta para o usuário (somente quando tipo=ambigua)"
}"""


class IntentClassifier:
    def __init__(self, ollama_client: OllamaClient, classifier_model_name: str):
        self.ollama_client = ollama_client
        self.classifier_model_name = classifier_model_name

    async def classify_user_message(self, user_message: str) -> dict:
        try:
            print(f"[Classifier] Classificando: {user_message[:200]}")
            result = await self.ollama_client.generate_completion_expecting_json(
                prompt=f"Mensagem do usuário: {user_message}",
                model_name=self.classifier_model_name,
                system_prompt=CLASSIFIER_SYSTEM_PROMPT,
            )
            print(f"[Classifier] Resultado: {str(result)[:300]}")
            return self._validate_and_normalize_classification(result)
        except Exception as error:
            print(f"[Classifier] Erro ao classificar: {error}")
            return self._get_fallback_classification()

    def _validate_and_normalize_classification(self, raw_result: dict) -> dict:
        valid_types = {"pergunta", "tarefa", "busca", "codigo", "imagem", "conversa", "ambigua"}
        valid_skills = {"shell", "web_search", None}

        intent_type = raw_result.get("tipo", "conversa")
        if intent_type not in valid_types:
            intent_type = "conversa"

        skill = raw_result.get("skill_sugerida")
        if skill not in valid_skills:
            skill = None

        # busca always uses web_search skill; this is a safety fallback in case the
        # classifier omits skill_sugerida for busca intents.
        if intent_type == "busca" and skill is None:
            skill = "web_search"

        pergunta_esclarecimento = raw_result.get("pergunta_esclarecimento")
        if not pergunta_esclarecimento or str(pergunta_esclarecimento).lower() in ("null", "none", ""):
            pergunta_esclarecimento = None

        return {
            "tipo": intent_type,
            "complexidade": raw_result.get("complexidade"),
            "precisa_skill": bool(raw_result.get("precisa_skill", False)),
            "skill_sugerida": skill,
            "resumo_intencao": raw_result.get("resumo_intencao", ""),
            "pergunta_esclarecimento": pergunta_esclarecimento,
        }

    def _get_fallback_classification(self) -> dict:
        return {
            "tipo": "conversa",
            "complexidade": None,
            "precisa_skill": False,
            "skill_sugerida": None,
            "resumo_intencao": "classificação falhou, tratando como conversa",
            "pergunta_esclarecimento": None,
        }
