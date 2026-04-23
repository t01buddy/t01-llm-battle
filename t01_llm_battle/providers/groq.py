import os

from pydantic_ai import Agent
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.groq import GroqProvider as PAIGroqProvider

from .base import BaseProvider, ProviderRequest, ProviderResult, ProviderType

_PRICING: dict[str, tuple[float, float]] = {
    # model: (input $/1M tokens, output $/1M tokens)
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "mixtral-8x7b-32768": (0.24, 0.24),
}

_DEFAULT_PRICING: tuple[float, float] = (0.10, 0.10)


class GroqProvider(BaseProvider):
    name = "groq"
    display_name = "Groq"
    provider_type = ProviderType.LLM

    def models(self) -> list[str]:
        return [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
        ]

    def _calc_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        input_rate, output_rate = _PRICING.get(model, _DEFAULT_PRICING)
        return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000

    async def run(self, request: ProviderRequest) -> ProviderResult:
        api_key = os.environ.get("GROQ_API_KEY", "")
        provider = PAIGroqProvider(api_key=api_key)
        model = GroqModel(request.model, provider=provider)
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
            content=result.output,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            credits_used=None,
            cost_usd=cost_usd,
            model=request.model,
            provider="groq",
        )
