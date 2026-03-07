import aiohttp
from skills.base_skill import BaseSkill

MAX_SEARCH_ATTEMPTS = 3
MAX_CONTENT_PER_RESULT = 400


class WebSearchSkill(BaseSkill):
    def __init__(self, config: dict):
        super().__init__(config)
        web_cfg = config.get("skills", {}).get("web_search", {})
        self.searxng_url = web_cfg.get("searxng_url", "http://searxng:8080").rstrip("/")
        self.max_results = web_cfg.get("max_results", 5)
        self.timeout_seconds = web_cfg.get("timeout_seconds", 30)

    @property
    def skill_name(self) -> str:
        return "web_search"

    @property
    def skill_description(self) -> str:
        return "Busca informações atualizadas na internet usando SearXNG"

    async def execute(self, query: str) -> str:
        query = query.strip()
        if not query:
            return "[WebSearch] Query de busca vazia."

        for attempt in range(1, MAX_SEARCH_ATTEMPTS + 1):
            try:
                result = await self._search(query)
                return result
            except aiohttp.ClientConnectorError:
                return (
                    f"[WebSearch] Não foi possível conectar ao SearXNG em {self.searxng_url}. "
                    "Verifique se o serviço está rodando."
                )
            except aiohttp.ClientResponseError as error:
                if attempt < MAX_SEARCH_ATTEMPTS:
                    continue
                return f"[WebSearch] Erro HTTP {error.status} ao buscar por: {query}"
            except Exception as error:
                if attempt < MAX_SEARCH_ATTEMPTS:
                    continue
                return f"[WebSearch] Erro inesperado após {MAX_SEARCH_ATTEMPTS} tentativas: {error}"

        return f"[WebSearch] Nenhum resultado obtido para: {query}"

    async def _search(self, query: str) -> str:
        params = {
            "q": query,
            "format": "json",
            "categories": "general",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.searxng_url}/search",
                params=params,
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
            ) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)

        results = data.get("results", [])[: self.max_results]
        if not results:
            return f"[WebSearch] Nenhum resultado encontrado para: {query}"

        lines = [f"Resultados da busca por: '{query}'\n"]
        for i, item in enumerate(results, 1):
            title = item.get("title", "Sem título")
            url = item.get("url", "")
            content = (item.get("content") or "Sem descrição")[:MAX_CONTENT_PER_RESULT]
            if len(item.get("content") or "") > MAX_CONTENT_PER_RESULT:
                content += "..."
            lines.append(f"{i}. {title}\n   URL: {url}\n   {content}")

        return "\n\n".join(lines)
