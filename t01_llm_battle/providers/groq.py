import os

import httpx

from .base import BaseProvider, CompletionRequest, CompletionResult

_API_URL = "https://api.groq.com/openai/v1/chat/completions"

_PRICING: dict[str, tuple[float, float]] = {
    # model: (input $/1M tokens, output $/1M tokens)
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "mixtral-8x7b-32768": (0.24, 0.24),
}

_DEFAULT_PRICING: tuple[float, float] = (0.10, 0.10)


class GroqProvider(BaseProvider):
    name = "groq"

    def models(self) -> list[str]:
        return [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
        ]

    def cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        input_rate, output_rate = _PRICING.get(model, _DEFAULT_PRICING)
        return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        api_key = os.environ.get("GROQ_API_KEY", "")

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
            raise RuntimeError(f"Groq API error {response.status_code}: {err}")

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
            provider="groq",
        )
