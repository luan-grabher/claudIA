import aiohttp
import json


class OllamaClient:
    def __init__(self, base_url: str, think_mode=None, think_for_json: bool = False, log_thinking: bool = False):
        self.base_url = base_url.rstrip("/")
        self.think_mode = think_mode
        self.think_for_json = think_for_json
        self.log_thinking = log_thinking

    def _apply_think_to_payload(self, payload: dict, expects_json: bool = False, forcar_desativar_think: bool = False):
        if forcar_desativar_think or self.think_mode is None:
            return
        if expects_json and not self.think_for_json:
            return
        payload["think"] = self.think_mode

    async def generate_completion(self, prompt: str, model_name: str, system_prompt: str = None, forcar_desativar_think: bool = False) -> dict:
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt
        self._apply_think_to_payload(payload, forcar_desativar_think=forcar_desativar_think)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                thinking_gerado = data.get("thinking")
                if self.log_thinking and thinking_gerado:
                    print(f"[DEBUG] Pensamento (generate): {str(thinking_gerado)[:500]}")
                return {
                    "content": data["response"].strip(),
                    "thinking": thinking_gerado,
                }

    async def generate_completion_expecting_json(self, prompt: str, model_name: str, system_prompt: str = None) -> dict:
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        if system_prompt:
            payload["system"] = system_prompt
        self._apply_think_to_payload(payload, expects_json=True)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return json.loads(data["response"])

    async def generate_chat_completion(self, messages: list, model_name: str, system_prompt: str = None, forcar_desativar_think: bool = False) -> dict:
        payload = {
            "model": model_name,
            "messages": messages,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt
        self._apply_think_to_payload(payload, forcar_desativar_think=forcar_desativar_think)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                thinking_gerado = data.get("message", {}).get("thinking")
                if self.log_thinking and thinking_gerado:
                    print(f"[DEBUG] Pensamento (chat): {str(thinking_gerado)[:500]}")
                return {
                    "content": data["message"]["content"].strip(),
                    "thinking": thinking_gerado,
                }

    async def check_if_model_is_available(self, model_name: str) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags") as response:
                    data = await response.json()
                    available_models = [m["name"] for m in data.get("models", [])]
                    return model_name in available_models
        except Exception:
            return False

    async def pull_model_if_not_available(self, model_name: str):
        if not await self.check_if_model_is_available(model_name):
            print(f"[ClaudIA] Baixando modelo {model_name}...")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/pull",
                    json={"name": model_name, "stream": False},
                    timeout=aiohttp.ClientTimeout(total=3600),
                ) as response:
                    response.raise_for_status()
                    print(f"[ClaudIA] Modelo {model_name} baixado com sucesso.")