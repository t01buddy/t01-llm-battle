import os

from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider as PAIAnthropicProvider

from .base import BaseProvider, ProviderRequest, ProviderResult, ProviderType
from ..pricing import get_llm_cost, get_llm_models


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    display_name = "Anthropic"
    provider_type = ProviderType.LLM

    def models(self) -> list[str]:
        return get_llm_models(self.name)

    async def run(self, request: ProviderRequest) -> ProviderResult:
        api_key = request.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")

        provider = PAIAnthropicProvider(api_key=api_key)
        model = AnthropicModel(request.model, provider=provider)
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
        cost_usd = get_llm_cost(self.name, request.model, input_tokens, output_tokens)

        return ProviderResult(
            content=result.output,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            credits_used=None,
            cost_usd=cost_usd,
            model=request.model,
            provider="anthropic",
        )
