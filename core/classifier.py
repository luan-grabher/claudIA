from models.ollama_client import OllamaClient

CLASSIFIER_SYSTEM_PROMPT = """Você é um classificador de intenções. Analise a mensagem do usuário e retorne APENAS um JSON válido, sem texto extra.

Tipos possíveis:
- "pergunta": usuário quer saber algo factual que pode ser respondido SEM executar nada no sistema
- "tarefa": usuário quer que você EXECUTE algo (instalar, criar, editar, rodar comandos, agendar, lembrar, verificar o estado do sistema)
- "codigo": usuário quer ajuda com código (escrever, debugar, revisar)
- "imagem": mensagem contém ou fala sobre imagem
- "conversa": saudação, bate-papo casual, feedback

REGRA PRINCIPAL: Se a mensagem pede para EXECUTAR, RODAR, LISTAR, VERIFICAR, INSTALAR ou FAZER algo no sistema, é sempre "tarefa".
Palavras-chave que indicam "tarefa": execute, rode, liste, instale, crie, edite, verifique, mostre, abra, feche, reinicie, pare, inicie.

REGRA: Se a pergunta é sobre o estado ATUAL do sistema (arquivos, pastas, processos, uso de CPU/memória), classifique como "tarefa" com skill "shell".

Exemplos:
- "execute o comando ls" → tarefa/shell (pediu para executar)
- "rode o comando X" → tarefa/shell (pediu para rodar)
- "quais pastas tem na raiz?" → tarefa/shell (precisa rodar ls /)
- "qual o uso de CPU?" → tarefa/shell (precisa rodar top/htop)
- "instale o pacote X" → tarefa/shell
- "me lembre de fazer X em 1 hora" → tarefa/shell
- "o que é Linux?" → pergunta (factual, não precisa executar nada)
- "como funciona o comando ls?" → pergunta (explicação, não execução)
- "oi tudo bem?" → conversa

Skills disponíveis para tarefas:
- "shell": executar comandos no terminal
- "web_search": buscar na internet

Complexidade (apenas para "pergunta"):
- "simples": resposta direta e curta
- "complexa": requer raciocínio ou múltiplos passos

Responda APENAS com este JSON:
{
  "tipo": "pergunta|tarefa|codigo|imagem|conversa",
  "complexidade": "simples|complexa|null",
  "precisa_skill": true|false,
  "skill_sugerida": "shell|web_search|null",
  "resumo_intencao": "uma frase descrevendo o que o usuário quer"
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
        valid_types = {"pergunta", "tarefa", "codigo", "imagem", "conversa"}
        valid_skills = {"shell", "web_search", None}

        intent_type = raw_result.get("tipo", "conversa")
        if intent_type not in valid_types:
            intent_type = "conversa"

        skill = raw_result.get("skill_sugerida")
        if skill not in valid_skills:
            skill = None

        return {
            "tipo": intent_type,
            "complexidade": raw_result.get("complexidade"),
            "precisa_skill": bool(raw_result.get("precisa_skill", False)),
            "skill_sugerida": skill,
            "resumo_intencao": raw_result.get("resumo_intencao", ""),
        }

    def _get_fallback_classification(self) -> dict:
        return {
            "tipo": "conversa",
            "complexidade": None,
            "precisa_skill": False,
            "skill_sugerida": None,
            "resumo_intencao": "classificação falhou, tratando como conversa",
        }
