import traceback
from models.ollama_client import OllamaClient

TASK_PLANNER_SYSTEM_PROMPT = """Você é um agente de IA autônomo com acesso ao terminal Linux.
O diretório de trabalho atual é /app. Todos os caminhos relativos partem deste diretório.

Dado uma tarefa, crie um plano de execução.

Regras importantes:
- Para qualquer informação sobre o sistema (arquivos, pastas, processos), use comandos shell.
- SEMPRE use caminhos relativos a /app para pastas do projeto (ex: ls skills/, ls core/, ls channels/).
- Use caminhos absolutos apenas para pastas do sistema (ex: ls /etc/, ls /var/).
- Nunca crie passos do tipo "raciocinio" com comando_ou_instrucao vazio, null ou nulo. Se o passo for shell, coloque o comando direto.
- Se o contexto da conversa anterior mencionar arquivos ou pastas, use essas informações para gerar comandos corretos.
- Seja autônomo: não peça confirmação, execute e resolva.

Responda APENAS com JSON válido:
{
  "plano_em_passos": [
    {
      "descricao": "o que este passo faz",
      "tipo": "shell",
      "comando_ou_instrucao": "comando exato (nunca null ou vazio)"
    }
  ],
  "estimativa_de_passos": 1
}"""

STEP_EVALUATOR_SYSTEM_PROMPT = """Você é um avaliador de progresso autônomo. Analise o resultado de um passo e decida o que fazer.

Se um comando falhou (exit code != 0 ou "not found" ou "command not found"):
- Gere um comando de recuperação que resolva o problema.
- Defina "deve_tentar_novamente": true e "comando_de_retry" com o comando corretivo.

IMPORTANTE: O campo "mensagem_para_usuario" DEVE conter um resumo útil do resultado.
Se o comando listou arquivos, inclua a lista na mensagem. Se instalou algo, confirme. Nunca deixe este campo vazio ou null.

Responda APENAS com JSON:
{
  "passo_foi_bem_sucedido": true|false,
  "devemos_continuar": true|false,
  "deve_tentar_novamente": true|false,
  "comando_de_retry": "null ou comando corretivo",
  "proximo_passo_ajustado": "null ou novo comando",
  "mensagem_para_usuario": "resumo completo do resultado, incluindo os dados obtidos"
}"""

FRIENDLY_SUMMARY_SYSTEM_PROMPT = """Você é ClaudIA, uma assistente de IA pessoal que roda localmente.
Apresente o resultado da tarefa de forma clara para o usuário em português.
IMPORTANTE: Inclua os dados reais obtidos (arquivos listados, valores, etc). Não resuma sem mostrar os dados."""

MAX_RETRIES_PER_STEP = 2


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
            return "\n\n".join(final_messages)

        if not all_step_results:
            return "Nenhum passo foi executado. Tente reformular a tarefa."

        print(f"[Orchestrator] Avaliador não gerou mensagens — gerando resumo a partir dos resultados brutos.")
        combined_raw_output = "\n\n".join(all_step_results)
        return await self._generate_user_friendly_summary(task_description, combined_raw_output)

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