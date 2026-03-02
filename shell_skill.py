import asyncio
import shlex
from skills.base_skill import BaseSkill

COMMANDS_THAT_ARE_NEVER_ALLOWED = [
    "rm -rf /",
    "rm -rf /*",
    "dd if=/dev/zero",
    "mkfs",
    ":(){:|:&};:",
    "chmod -R 777 /",
]


class ShellSkill(BaseSkill):
    def __init__(self, config: dict):
        super().__init__(config)
        self.timeout_seconds = config.get("skills", {}).get("shell", {}).get("timeout_seconds", 60)

    @property
    def skill_name(self) -> str:
        return "shell"

    @property
    def skill_description(self) -> str:
        return "Executa comandos no terminal do servidor Linux"

    async def execute(self, command: str) -> str:
        command = command.strip()

        if self._command_is_dangerous(command):
            return f"[Shell] Comando bloqueado por segurança: {command}"

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )

            stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()

            output_parts = []
            if stdout_text:
                output_parts.append(f"STDOUT:\n{stdout_text}")
            if stderr_text:
                output_parts.append(f"STDERR:\n{stderr_text}")

            output_parts.append(f"Exit code: {process.returncode}")

            return "\n".join(output_parts) if output_parts else "Comando executado sem saída."

        except asyncio.TimeoutError:
            return f"[Shell] Timeout após {self.timeout_seconds}s. Comando pode ainda estar rodando."
        except Exception as error:
            return f"[Shell] Erro ao executar: {error}"

    def _command_is_dangerous(self, command: str) -> bool:
        command_lower = command.lower()
        return any(blocked in command_lower for blocked in COMMANDS_THAT_ARE_NEVER_ALLOWED)
