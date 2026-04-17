import os

import httpx

from .base import BaseProvider, CompletionRequest, CompletionResult

PRICING = {
    "claude-opus-4-6": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
}

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def models(self) -> list[str]:
        return ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]

    def cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        if model not in PRICING:
            return 0.0
        input_rate, output_rate = PRICING[model]
        return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")

        payload = {
            "model": request.model,
            "system": request.system_prompt,
            "messages": [{"role": "user", "content": request.user_prompt}],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(API_URL, json=payload, headers=headers)

        if response.status_code != 200:
            data = response.json()
            error_msg = data.get("error", {}).get("message", response.text)
            raise RuntimeError(f"Anthropic API error {response.status_code}: {error_msg}")

        data = response.json()
        content = data["content"][0]["text"]
        input_tokens = data["usage"]["input_tokens"]
        output_tokens = data["usage"]["output_tokens"]
        cost_usd = self.cost(input_tokens, output_tokens, request.model)

        return CompletionResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            model=request.model,
            provider="anthropic",
        )
