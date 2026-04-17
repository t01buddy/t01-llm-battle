"""Google (Gemini) provider adapter — thin httpx client, no official SDK."""

import os

import httpx

from .base import BaseProvider, CompletionRequest, CompletionResult

_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    "/{model}:generateContent?key={api_key}"
)

_PRICING: dict[str, tuple[float, float]] = {
    # (input $/1M tokens, output $/1M tokens)
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
}


class GoogleProvider(BaseProvider):
    name = "google"

    def models(self) -> list[str]:
        return ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]

    def cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        if model not in _PRICING:
            return 0.0
        input_price, output_price = _PRICING[model]
        return (input_tokens * input_price + output_tokens * output_price) / 1_000_000

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        url = _ENDPOINT.format(model=request.model, api_key=api_key)

        payload: dict = {
            "contents": [
                {"role": "user", "parts": [{"text": request.user_prompt}]}
            ],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        if request.system_prompt:
            payload["system_instruction"] = {
                "parts": [{"text": request.system_prompt}]
            }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount", 0)
        output_tokens = usage.get("candidatesTokenCount", 0)
        cost_usd = self.cost(input_tokens, output_tokens, request.model)

        return CompletionResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            model=request.model,
            provider=self.name,
        )
