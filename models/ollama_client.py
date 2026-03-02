import aiohttp
import json


class OllamaClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def generate_completion(self, prompt: str, model_name: str, system_prompt: str = None) -> str:
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return data["response"].strip()

    async def generate_completion_expecting_json(self, prompt: str, model_name: str, system_prompt: str = None) -> dict:
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return json.loads(data["response"])

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
            print(f"[Axon] Baixando modelo {model_name}...")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/pull",
                    json={"name": model_name, "stream": False},
                    timeout=aiohttp.ClientTimeout(total=3600),
                ) as response:
                    response.raise_for_status()
                    print(f"[Axon] Modelo {model_name} baixado com sucesso.")
