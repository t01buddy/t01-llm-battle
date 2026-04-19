import os

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider as PAIOpenAIProvider

from .base import BaseProvider, ProviderRequest, ProviderResult, ProviderType

_PRICING: dict[str, tuple[float, float]] = {
    # model: (input $/1M tokens, output $/1M tokens)
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-3.5-turbo": (0.50, 1.50),
}


class OpenAIProvider(BaseProvider):
    name = "openai"
    display_name = "OpenAI"
    provider_type = ProviderType.LLM

    def models(self) -> list[str]:
        return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]

    def _calc_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        if model not in _PRICING:
            return 0.0
        input_rate, output_rate = _PRICING[model]
        return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000

    async def run(self, request: ProviderRequest) -> ProviderResult:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        provider = PAIOpenAIProvider(api_key=api_key)
        model = OpenAIChatModel(request.model, provider=provider)
        agent = Agent(model)

        result = await agent.run(
            request.user_prompt,
            system_prompt=request.system_prompt or "",
        )

        usage = result.usage()
        input_tokens = usage.request_tokens or 0
        output_tokens = usage.response_tokens or 0
        cost_usd = self._calc_cost(input_tokens, output_tokens, request.model)

        return ProviderResult(
            content=result.data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            credits_used=None,
            cost_usd=cost_usd,
            model=request.model,
            provider="openai",
        )
