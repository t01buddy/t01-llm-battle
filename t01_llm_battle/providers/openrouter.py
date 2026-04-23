import os

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider as PAIOpenAIProvider

from .base import BaseProvider, ProviderRequest, ProviderResult, ProviderType

_MODELS = [
    "openai/gpt-4o",
    "anthropic/claude-sonnet-4-6",
    "google/gemini-2.0-flash",
    "meta-llama/llama-3.3-70b-instruct",
    "mistralai/mistral-7b-instruct",
]


class OpenRouterProvider(BaseProvider):
    name = "openrouter"
    display_name = "OpenRouter"
    provider_type = ProviderType.LLM

    def models(self) -> list[str]:
        return list(_MODELS)

    async def run(self, request: ProviderRequest) -> ProviderResult:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        provider = PAIOpenAIProvider(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
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
            provider="openrouter",
        )
