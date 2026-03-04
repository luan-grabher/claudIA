import aiohttp
import json


class OllamaClient:
    def __init__(self, base_url: str, think_mode=None, think_for_json: bool = False, log_thinking: bool = False):
        self.base_url = base_url.rstrip("/")
        self.think_mode = think_mode
        self.think_for_json = think_for_json
        self.log_thinking = log_thinking

    def _apply_think_to_payload(self, payload: dict, forcar_desativar_think: bool = False):
        if forcar_desativar_think:
            payload["think"] = False
            return
        if self.think_mode is not None:
            payload["think"] = self.think_mode

    def _apply_think_to_json_payload(self, payload: dict):
        if self.think_for_json and self.think_mode is not None:
            payload["think"] = self.think_mode
        else:
            payload["think"] = False

    def _build_messages_with_system_prepended(self, messages: list, system_prompt: str) -> list:
        return [{"role": "system", "content": system_prompt}] + messages

    def _extract_first_json_object_from_text(self, text: str) -> dict:
        opening_brace_index = text.find("{")
        closing_brace_index = text.rfind("}")
        if opening_brace_index == -1 or closing_brace_index == -1:
            raise ValueError(f"Nenhum JSON encontrado na resposta. Resposta completa: {text[:500]}")
        json_substring = text[opening_brace_index:closing_brace_index + 1]
        try:
            return json.loads(json_substring)
        except json.JSONDecodeError as parse_error:
            raise ValueError(f"JSON inválido extraído da resposta. Erro: {parse_error}. JSON extraído: {json_substring[:500]}")

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
                    print(f"[OllamaClient] Pensamento (generate/{model_name}): {str(thinking_gerado)[:500]}")
                return {
                    "content": data["response"].strip(),
                    "thinking": thinking_gerado,
                }

    async def generate_completion_expecting_json(self, prompt: str, model_name: str, system_prompt: str = None) -> dict:
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt
        self._apply_think_to_json_payload(payload)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                thinking_gerado = data.get("thinking")
                if self.log_thinking and thinking_gerado:
                    print(f"[OllamaClient] Pensamento (json/{model_name}): {str(thinking_gerado)[:500]}")
                raw_response_text = data.get("response", "").strip()
                if not raw_response_text:
                    raise ValueError(f"Modelo '{model_name}' retornou resposta vazia ao gerar JSON. Payload enviado: think={payload.get('think')}")
                return self._extract_first_json_object_from_text(raw_response_text)

    async def generate_chat_completion(self, messages: list, model_name: str, system_prompt: str = None, forcar_desativar_think: bool = False) -> dict:
        messages_with_system = (
            self._build_messages_with_system_prepended(messages, system_prompt)
            if system_prompt
            else messages
        )
        payload = {
            "model": model_name,
            "messages": messages_with_system,
            "stream": False,
        }
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
                    print(f"[OllamaClient] Pensamento (chat/{model_name}): {str(thinking_gerado)[:500]}")
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