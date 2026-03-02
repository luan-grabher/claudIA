import json
from models.ollama_client import OllamaClient

TASK_PLANNER_SYSTEM_PROMPT = """Você é um agente de IA com acesso ao terminal Linux. Dado uma tarefa, crie um plano de execução.

Responda APENAS com JSON válido:
{
  "plano_em_passos": [
    {
      "descricao": "o que este passo faz",
      "tipo": "shell|raciocinio",
      "comando_ou_instrucao": "comando exato ou instrução"
    }
  ],
  "estimativa_de_passos": 3
}

Use "shell" para comandos de terminal. Use "raciocinio" para quando só precisa pensar/responder."""

STEP_EVALUATOR_SYSTEM_PROMPT = """Você é um avaliador de progresso. Analise o resultado de um passo e decida se devemos continuar.

Responda APENAS com JSON:
{
  "passo_foi_bem_sucedido": true|false,
  "devemos_continuar": true|false,
  "proximo_passo_ajustado": "null ou novo comando/instrução se precisar ajustar",
  "mensagem_para_usuario": "resumo do que aconteceu"
}"""


class TaskOrchestrator:
    def __init__(self, ollama_client: OllamaClient, skills_registry: dict, config: dict):
        self.ollama_client = ollama_client
        self.skills_registry = skills_registry
        self.default_model_name = config["models"]["default"]["name"]
        self.max_steps = config.get("orchestrator", {}).get("max_steps_per_task", 8)

    async def execute_task_with_planning(self, task_description: str, suggested_skill: str = None) -> str:
        if suggested_skill and suggested_skill in self.skills_registry:
            return await self._execute_direct_skill(task_description, suggested_skill)

        return await self._execute_with_full_planning_loop(task_description)

    async def _execute_direct_skill(self, task_description: str, skill_name: str) -> str:
        skill = self.skills_registry[skill_name]
        command = await self._extract_command_for_skill(task_description, skill_name)
        result = await skill.execute(command)

        summary = await self._generate_user_friendly_summary(task_description, result)
        return summary

    async def _extract_command_for_skill(self, task_description: str, skill_name: str) -> str:
        prompt = f"""Extraia o comando {skill_name} exato para executar a seguinte tarefa.
Responda APENAS com o comando, sem explicação.

Tarefa: {task_description}"""

        return await self.ollama_client.generate_completion(
            prompt=prompt,
            model_name=self.default_model_name,
        )

    async def _execute_with_full_planning_loop(self, task_description: str) -> str:
        plan = await self._generate_execution_plan(task_description)
        steps = plan.get("plano_em_passos", [])

        if not steps:
            return await self.ollama_client.generate_completion(
                prompt=task_description,
                model_name=self.default_model_name,
            )

        execution_history = []
        final_messages = []

        for step_index, step in enumerate(steps[:self.max_steps]):
            step_result = await self._execute_single_step(step)
            execution_history.append({"step": step, "result": step_result})

            evaluation = await self._evaluate_step_result(
                task_description=task_description,
                step=step,
                step_result=step_result,
                step_index=step_index,
            )

            if evaluation.get("mensagem_para_usuario"):
                final_messages.append(evaluation["mensagem_para_usuario"])

            if not evaluation.get("devemos_continuar", True):
                break

            adjusted_next = evaluation.get("proximo_passo_ajustado")
            if adjusted_next and adjusted_next != "null" and step_index + 1 < len(steps):
                steps[step_index + 1]["comando_ou_instrucao"] = adjusted_next

        return "\n\n".join(final_messages) if final_messages else "Tarefa concluída."

    async def _generate_execution_plan(self, task_description: str) -> dict:
        try:
            return await self.ollama_client.generate_completion_expecting_json(
                prompt=f"Tarefa: {task_description}",
                model_name=self.default_model_name,
                system_prompt=TASK_PLANNER_SYSTEM_PROMPT,
            )
        except Exception as error:
            print(f"[Orchestrator] Erro ao gerar plano: {error}")
            return {"plano_em_passos": []}

    async def _execute_single_step(self, step: dict) -> str:
        step_type = step.get("tipo", "raciocinio")
        instruction = step.get("comando_ou_instrucao", "")

        if step_type == "shell" and "shell" in self.skills_registry:
            return await self.skills_registry["shell"].execute(instruction)

        return await self.ollama_client.generate_completion(
            prompt=instruction,
            model_name=self.default_model_name,
        )

    async def _evaluate_step_result(self, task_description: str, step: dict, step_result: str, step_index: int) -> dict:
        try:
            prompt = f"""Tarefa original: {task_description}
Passo {step_index + 1}: {step.get("descricao", "")}
Resultado: {step_result[:2000]}"""

            return await self.ollama_client.generate_completion_expecting_json(
                prompt=prompt,
                model_name=self.default_model_name,
                system_prompt=STEP_EVALUATOR_SYSTEM_PROMPT,
            )
        except Exception:
            return {
                "passo_foi_bem_sucedido": True,
                "devemos_continuar": True,
                "proximo_passo_ajustado": None,
                "mensagem_para_usuario": step_result,
            }

    async def _generate_user_friendly_summary(self, task_description: str, raw_output: str) -> str:
        prompt = f"""Tarefa: {task_description}

Saída do terminal:
{raw_output[:3000]}

Explique o resultado em linguagem natural e amigável para o usuário, em português."""

        return await self.ollama_client.generate_completion(
            prompt=prompt,
            model_name=self.default_model_name,
        )
