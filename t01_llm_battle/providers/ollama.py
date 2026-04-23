import httpx
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider as PAIOpenAIProvider

from ..db import resolve_base_url
from .base import BaseProvider, ProviderRequest, ProviderResult, ProviderType

_DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider(BaseProvider):
    name = "ollama"
    display_name = "Ollama"
    provider_type = ProviderType.LLM

    def __init__(self, base_url: str = _DEFAULT_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    async def _effective_base_url(self) -> str:
        """Return base_url from DB if configured, otherwise use instance default."""
        db_url = await resolve_base_url("ollama")
        return (db_url or self.base_url).rstrip("/")

    def models(self) -> list[str]:
        """Query Ollama's /api/tags for installed models; return [] if not running."""
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            if response.status_code != 200:
                return []
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    async def run(self, request: ProviderRequest) -> ProviderResult:
        base_url = await self._effective_base_url()
        provider = PAIOpenAIProvider(
            base_url=f"{base_url}/v1",
            api_key="ollama",  # Ollama doesn't need a real key
        )
        model = OpenAIChatModel(request.model, provider=provider)
        agent = Agent(model, system_prompt=request.system_prompt or "")

        model_settings: dict = {
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if "top_p" in request.extra:
            model_settings["top_p"] = request.extra["top_p"]

        result = await agent.run(
            request.user_prompt,
            model_settings=model_settings,
        )

        usage = result.usage()
        input_tokens = usage.request_tokens or 0
        output_tokens = usage.response_tokens or 0

        return ProviderResult(
            content=result.data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            credits_used=None,
            cost_usd=0.0,
            model=request.model,
            provider="ollama",
        )
