import os

import httpx

from .base import BaseProvider, CompletionRequest, CompletionResult

_API_URL = "https://api.openai.com/v1/chat/completions"

_PRICING: dict[str, tuple[float, float]] = {
    # model: (input $/1M tokens, output $/1M tokens)
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-3.5-turbo": (0.50, 1.50),
}


class OpenAIProvider(BaseProvider):
    name = "openai"

    def models(self) -> list[str]:
        return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]

    def cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        if model not in _PRICING:
            return 0.0
        input_rate, output_rate = _PRICING[model]
        return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        api_key = os.environ.get("OPENAI_API_KEY", "")

        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.user_prompt})

        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                _API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if response.status_code != 200:
            try:
                err = response.json().get("error", {}).get("message", response.text)
            except Exception:
                err = response.text
            raise RuntimeError(f"OpenAI API error {response.status_code}: {err}")

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        cost_usd = self.cost(input_tokens, output_tokens, request.model)

        return CompletionResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            model=request.model,
            provider="openai",
        )
