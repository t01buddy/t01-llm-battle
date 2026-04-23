"""Google (Gemini) provider adapter — uses Pydantic AI."""

import os

from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.providers.google_gla import GoogleGLAProvider

from .base import BaseProvider, ProviderRequest, ProviderResult, ProviderType

_PRICING: dict[str, tuple[float, float]] = {
    # (input $/1M tokens, output $/1M tokens)
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
}


class GoogleProvider(BaseProvider):
    name = "google"
    display_name = "Google"
    provider_type = ProviderType.LLM

    def models(self) -> list[str]:
        return ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]

    def _calc_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        if model not in _PRICING:
            return 0.0
        input_price, output_price = _PRICING[model]
        return (input_tokens * input_price + output_tokens * output_price) / 1_000_000

    async def run(self, request: ProviderRequest) -> ProviderResult:
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        provider = GoogleGLAProvider(api_key=api_key)
        model = GeminiModel(request.model, provider=provider)
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
            provider=self.name,
        )
