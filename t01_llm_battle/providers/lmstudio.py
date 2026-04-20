"""LLM Studio provider adapter — OpenAI-compatible local server."""
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider as PAIOpenAIProvider

from ..db import resolve_base_url
from .base import BaseProvider, ProviderRequest, ProviderResult, ProviderType

_DEFAULT_BASE_URL = "http://localhost:1234"


class LMStudioProvider(BaseProvider):
    name = "llm-studio"
    display_name = "LM Studio"
    provider_type = ProviderType.LLM

    def __init__(self, base_url: str = _DEFAULT_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    async def _effective_base_url(self) -> str:
        """Return base_url from DB if configured, otherwise use instance default."""
        db_url = await resolve_base_url("llm-studio")
        return (db_url or self.base_url).rstrip("/")

    def models(self) -> list[str]:
        """LM Studio doesn't expose a standard model list endpoint; return empty."""
        return []

    async def run(self, request: ProviderRequest) -> ProviderResult:
        base_url = await self._effective_base_url()
        provider = PAIOpenAIProvider(
            base_url=f"{base_url}/v1",
            api_key="lm-studio",  # LM Studio doesn't need a real key
        )
        model = OpenAIChatModel(request.model, provider=provider)
        agent = Agent(model)

        model_settings: dict = {
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if "top_p" in request.extra:
            model_settings["top_p"] = request.extra["top_p"]

        result = await agent.run(
            request.user_prompt,
            system_prompt=request.system_prompt or "",
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
            provider="llm-studio",
        )
