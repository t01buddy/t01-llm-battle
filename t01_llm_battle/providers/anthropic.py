import os

from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider as PAIAnthropicProvider

from .base import BaseProvider, ProviderRequest, ProviderResult, ProviderType

PRICING = {
    "claude-opus-4-6": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
}


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    display_name = "Anthropic"
    provider_type = ProviderType.LLM

    def models(self) -> list[str]:
        return ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]

    def _calc_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        if model not in PRICING:
            return 0.0
        input_rate, output_rate = PRICING[model]
        return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000

    async def run(self, request: ProviderRequest) -> ProviderResult:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
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
        cost_usd = self._calc_cost(input_tokens, output_tokens, request.model)

        return ProviderResult(
            content=result.data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            credits_used=None,
            cost_usd=cost_usd,
            model=request.model,
            provider="anthropic",
        )
