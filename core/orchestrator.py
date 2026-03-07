import traceback
from models.ollama_client import OllamaClient

TASK_PLANNER_SYSTEM_PROMPT = """Você é um agente de IA autônomo. Antes de criar o plano, analise mentalmente:
1. Esta tarefa precisa de informação do sistema (arquivos, processos, memória)? → use "shell"
2. Esta tarefa precisa de informações atuais da internet? → use "web_search"
3. Esta tarefa pode ser respondida só com raciocínio? → use "raciocinio"

O diretório de trabalho atual é /app. Todos os caminhos relativos partem deste diretório.

Tipos de passos disponíveis:
- "shell": executa comando no terminal Linux
- "web_search": busca na internet — forneça uma query específica como instrução
- "raciocinio": raciocínio interno — forneça uma instrução clara e completa

Regras:
- Para qualquer informação sobre o sistema (arquivos, pastas, processos, uso de CPU/memória), use "shell".
- Para notícias, preços, informações externas ou atuais, use "web_search".
- Use caminhos relativos a /app para arquivos do projeto (ex: ls skills/, ls core/).
- Use caminhos absolutos apenas para o sistema (ex: ls /etc/).
- NUNCA deixe "comando_ou_instrucao" vazio, null ou nulo.
- Seja autônomo: não peça confirmação, execute e resolva.
- Para "web_search": escreva uma query de busca objetiva e específica.
- Para "raciocinio": escreva a instrução completa do que o modelo deve fazer.

Responda APENAS com JSON válido:
{
  "plano_em_passos": [
    {
      "descricao": "o que este passo faz",
      "tipo": "shell|web_search|raciocinio",
      "comando_ou_instrucao": "comando, query de busca, ou instrução (nunca null ou vazio)"
    }
  ],
  "estimativa_de_passos": 1
}"""

STEP_EVALUATOR_SYSTEM_PROMPT = """Você é um avaliador de progresso autônomo. Analise o resultado de um passo e decida o que fazer.

Se um comando shell falhou (exit code != 0, "not found" ou "command not found"):
- Gere um comando de recuperação que resolva o problema.
- Defina "deve_tentar_novamente": true e "comando_de_retry" com o comando corretivo.

Se uma busca web retornou vazio ou "[WebSearch] Nenhum resultado":
- Reformule a query de busca e defina "deve_tentar_novamente": true.
- Coloque a nova query em "comando_de_retry".

IMPORTANTE: O campo "mensagem_para_usuario" DEVE conter um resumo útil do resultado.
Se o passo listou arquivos, inclua a lista. Se foi busca, inclua os dados encontrados. Nunca deixe vazio ou null.

Responda APENAS com JSON:
{
  "passo_foi_bem_sucedido": true|false,
  "devemos_continuar": true|false,
  "deve_tentar_novamente": true|false,
  "comando_de_retry": "null ou comando/query corretivo",
  "proximo_passo_ajustado": "null ou novo comando",
  "mensagem_para_usuario": "resumo completo do resultado, incluindo os dados obtidos"
}"""

RESPONSE_VALIDATOR_SYSTEM_PROMPT = """Você é um validador de respostas. Verifique se a resposta gerada resolve o que o usuário pediu.

Checklist:
- A resposta responde exatamente o que foi pedido?
- Não contém dados inventados ou alucinação?
- Se usou ferramenta (shell/web), o resultado real foi incorporado?
- Está concisa, sem informações desnecessárias?

Responda APENAS com JSON:
{
  "aprovado_para_envio": true|false,
  "motivo_reprovacao": "null ou descrição do problema"
}"""

FRIENDLY_SUMMARY_SYSTEM_PROMPT = """Você é ClaudIA, uma assistente de IA pessoal que roda localmente.
Apresente o resultado da tarefa de forma clara para o usuário em português.

Antes de responder, verifique internamente:
- O que produzi responde exatamente o que foi pedido?
- Contém os dados reais obtidos (não inventados)?
- Está conciso e no formato adequado?

IMPORTANTE: Inclua os dados reais obtidos (arquivos listados, resultados de busca, valores, etc). Não resuma sem mostrar os dados."""

MAX_RETRIES_PER_STEP = 2
MAX_RESPONSE_VALIDATION_RETRIES = 2


class TaskOrchestrator:
    def __init__(self, ollama_client: OllamaClient, skills_registry: dict, config: dict):
        self.ollama_client = ollama_client
        self.skills_registry = skills_registry
        self.default_model_name = config["models"]["default"]["name"]
        self.max_steps = config.get("orchestrator", {}).get("max_steps_per_task", 8)

    async def execute_task_with_planning(
        self,
        task_description: str,
        suggested_skill: str = None,
        recent_conversation_history: list = None,
    ) -> str:
        print(f"[Orchestrator] Iniciando execução de tarefa. Skill sugerida: {suggested_skill}")
        return await self._execute_with_full_planning_loop(
            task_description,
            suggested_skill,
            recent_conversation_history or [],
        )

    def _build_conversation_context_block(self, recent_history: list) -> str:
        if not recent_history:
            return ""
        last_exchanges = recent_history[-6:]
        lines = []
        for message in last_exchanges:
            role_label = "Usuário" if message["role"] == "user" else "Assistente"
            lines.append(f"{role_label}: {message['content'][:500]}")
        return "\n\nContexto da conversa recente:\n" + "\n".join(lines)

    async def _execute_with_full_planning_loop(
        self,
        task_description: str,
        skill_hint: str = None,
        recent_conversation_history: list = None,
    ) -> str:
        plan = await self._generate_execution_plan(
            task_description,
            skill_hint,
            recent_conversation_history or [],
        )
        steps = plan.get("plano_em_passos", [])

        if not steps:
            print(f"[Orchestrator] Plano vazio, chamando modelo diretamente.")
            resultado = await self.ollama_client.generate_completion(
                prompt=task_description,
                model_name=self.default_model_name,
            )
            return resultado["content"]

        print(f"[Orchestrator] Plano gerado com {len(steps)} passos.")
        all_step_results = []
        final_messages = []

        for step_index, step in enumerate(steps[:self.max_steps]):
            instruction = step.get("comando_ou_instrucao", "").strip()

            if not instruction or instruction.lower() in ("null", "none", ""):
                print(f"[Orchestrator] Pulando passo {step_index + 1} — instrução vazia ou nula.")
                continue

            print(f"[Orchestrator] Executando passo {step_index + 1}/{len(steps)}: {step.get('descricao')}")
            step_result, evaluation = await self._execute_step_with_retry(
                task_description=task_description,
                step=step,
                step_index=step_index,
            )
            all_step_results.append(step_result)
            print(f"[Orchestrator] Resultado do passo {step_index + 1} (trecho): {step_result[:300]}")

            mensagem_do_avaliador = evaluation.get("mensagem_para_usuario", "").strip()
            if mensagem_do_avaliador and mensagem_do_avaliador.lower() not in ("null", "none", ""):
                final_messages.append(mensagem_do_avaliador)

            if not evaluation.get("devemos_continuar", True):
                print(f"[Orchestrator] Avaliador sinalizou parada após passo {step_index + 1}.")
                break

            adjusted_next = evaluation.get("proximo_passo_ajustado")
            if adjusted_next and adjusted_next not in ("null", "none", "") and step_index + 1 < len(steps):
                print(f"[Orchestrator] Ajustando próximo passo para: {str(adjusted_next)[:200]}")
                steps[step_index + 1]["comando_ou_instrucao"] = adjusted_next

        if final_messages:
            raw_response = "\n\n".join(final_messages)
            return await self._validate_and_refine_response(task_description, raw_response)

        if not all_step_results:
            return "Nenhum passo foi executado. Tente reformular a tarefa."

        print(f"[Orchestrator] Avaliador não gerou mensagens — gerando resumo a partir dos resultados brutos.")
        combined_raw_output = "\n\n".join(all_step_results)
        summary = await self._generate_user_friendly_summary(task_description, combined_raw_output)
        return await self._validate_and_refine_response(task_description, summary)

    async def _generate_execution_plan(
        self,
        task_description: str,
        skill_hint: str = None,
        recent_conversation_history: list = None,
    ) -> dict:
        skill_context = f"\nSkill disponível e preferencial para esta tarefa: {skill_hint}" if skill_hint else ""
        conversation_context = self._build_conversation_context_block(recent_conversation_history or [])
        try:
            print(f"[Orchestrator] Solicitando plano ao modelo...")
            plan = await self.ollama_client.generate_completion_expecting_json(
                prompt=f"Tarefa: {task_description}{skill_context}{conversation_context}",
                model_name=self.default_model_name,
                system_prompt=TASK_PLANNER_SYSTEM_PROMPT,
            )
            print(f"[Orchestrator] Plano recebido: {str(plan)[:400]}")
            return plan
        except Exception as error:
            print(f"[Orchestrator] Erro ao gerar plano: {error}")
            print(traceback.format_exc())
            return {"plano_em_passos": []}

    async def _execute_step_with_retry(self, task_description: str, step: dict, step_index: int) -> tuple:
        step = dict(step)
        last_result = ""
        last_evaluation: dict = {"passo_foi_bem_sucedido": True, "devemos_continuar": True}

        for attempt in range(MAX_RETRIES_PER_STEP + 1):
            print(f"[Orchestrator] Tentativa {attempt + 1} — tipo={step.get('tipo')} comando={str(step.get('comando_ou_instrucao', ''))[:200]}")
            last_result = await self._execute_single_step(step)
            last_evaluation = await self._evaluate_step_result(
                task_description=task_description,
                step=step,
                step_result=last_result,
                step_index=step_index,
            )

            should_retry = last_evaluation.get("deve_tentar_novamente", False)
            retry_command = last_evaluation.get("comando_de_retry")

            if should_retry and retry_command not in (None, "null", "") and attempt < MAX_RETRIES_PER_STEP:
                print(f"[Orchestrator] Recovery (tentativa {attempt + 1}): {str(retry_command)[:200]}")
                step["comando_ou_instrucao"] = retry_command
                # Preserve web_search type; only switch to shell if the step was originally shell
                if step.get("tipo") not in ("web_search", "shell"):
                    step["tipo"] = "shell"
                continue

            break

        return last_result, last_evaluation

    async def _execute_single_step(self, step: dict) -> str:
        step_type = step.get("tipo", "raciocinio")
        instruction = step.get("comando_ou_instrucao", "")

        if step_type == "shell" and "shell" in self.skills_registry:
            print(f"[Orchestrator] Chamando skill 'shell': {instruction[:200]}")
            return await self.skills_registry["shell"].execute(instruction)

        if step_type == "web_search" and "web_search" in self.skills_registry:
            print(f"[Orchestrator] Chamando skill 'web_search': {instruction[:200]}")
            return await self.skills_registry["web_search"].execute(instruction)

        if step_type == "web_search" and "web_search" not in self.skills_registry:
            return "[WebSearch] Skill de busca na web não está habilitada. Configure web_search no config.yml."

        print(f"[Orchestrator] Chamando modelo para raciocínio: {instruction[:200]}")
        resultado = await self.ollama_client.generate_completion(
            prompt=instruction,
            model_name=self.default_model_name,
        )
        return resultado["content"]

    async def _evaluate_step_result(self, task_description: str, step: dict, step_result: str, step_index: int) -> dict:
        try:
            print(f"[Orchestrator] Avaliando resultado do passo {step_index + 1}...")
            prompt = f"""Tarefa original: {task_description}
Passo {step_index + 1}: {step.get("descricao", "")}
Comando executado: {step.get("comando_ou_instrucao", "")}
Resultado: {step_result[:2000]}"""

            return await self.ollama_client.generate_completion_expecting_json(
                prompt=prompt,
                model_name=self.default_model_name,
                system_prompt=STEP_EVALUATOR_SYSTEM_PROMPT,
            )
        except Exception as error:
            print(f"[Orchestrator] Erro ao avaliar passo {step_index + 1}: {error}")
            print(traceback.format_exc())
            return {
                "passo_foi_bem_sucedido": True,
                "devemos_continuar": False,
                "deve_tentar_novamente": False,
                "comando_de_retry": None,
                "proximo_passo_ajustado": None,
                "mensagem_para_usuario": step_result,
            }

    async def _validate_and_refine_response(self, task_description: str, response: str) -> str:
        for attempt in range(MAX_RESPONSE_VALIDATION_RETRIES):
            try:
                print(f"[Orchestrator] Validando resposta (tentativa {attempt + 1})...")
                validation = await self.ollama_client.generate_completion_expecting_json(
                    prompt=f"Tarefa original: {task_description}\n\nResposta gerada:\n{response[:3000]}",
                    model_name=self.default_model_name,
                    system_prompt=RESPONSE_VALIDATOR_SYSTEM_PROMPT,
                )
                if validation.get("aprovado_para_envio", False):
                    print(f"[Orchestrator] Resposta aprovada na validação.")
                    return response

                motivo = validation.get("motivo_reprovacao", "resposta incompleta")
                print(f"[Orchestrator] Resposta reprovada: {motivo}. Refinando...")
                response = await self._refine_response(task_description, response, motivo)
            except Exception as error:
                print(f"[Orchestrator] Erro na validação da resposta: {error}")
                break

        return response

    async def _refine_response(self, task_description: str, previous_response: str, problem: str) -> str:
        prompt = (
            f"Tarefa original: {task_description}\n\n"
            f"Resposta anterior (com problema):\n{previous_response[:2000]}\n\n"
            f"Problema identificado: {problem}\n\n"
            "Reescreva a resposta corrigindo o problema identificado. "
            "Inclua os dados reais, seja direto e responda exatamente o que foi pedido."
        )
        resultado = await self.ollama_client.generate_completion(
            prompt=prompt,
            model_name=self.default_model_name,
            system_prompt=FRIENDLY_SUMMARY_SYSTEM_PROMPT,
        )
        return resultado["content"]

    async def _generate_user_friendly_summary(self, task_description: str, raw_output: str) -> str:
        print(f"[Orchestrator] Gerando resumo amigável para o usuário...")
        prompt = f"""Tarefa executada: {task_description}

Saída obtida:
{raw_output[:3000]}

Apresente o resultado de forma clara para o usuário, incluindo os dados reais obtidos."""

        resultado = await self.ollama_client.generate_completion(
            prompt=prompt,
            model_name=self.default_model_name,
            system_prompt=FRIENDLY_SUMMARY_SYSTEM_PROMPT,
        )
        return resultado["content"]