import os

import httpx

from .base import BaseProvider, CompletionRequest, CompletionResult

_API_URL = "https://openrouter.ai/api/v1/chat/completions"

_MODELS = [
    "openai/gpt-4o",
    "anthropic/claude-sonnet-4-6",
    "google/gemini-2.0-flash",
    "meta-llama/llama-3.3-70b-instruct",
    "mistralai/mistral-7b-instruct",
]


class OpenRouterProvider(BaseProvider):
    name = "openrouter"

    def models(self) -> list[str]:
        return list(_MODELS)

    def cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        # OpenRouter pricing varies per model and is fetched dynamically in a real app.
        # For v0.1, return 0.0 (unknown).
        return 0.0

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")

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
                    "HTTP-Referer": "http://localhost:7700",
                    "X-Title": "t01-llm-battle",
                },
                json=payload,
            )

        if response.status_code != 200:
            try:
                err = response.json().get("error", {}).get("message", response.text)
            except Exception:
                err = response.text
            raise RuntimeError(f"OpenRouter API error {response.status_code}: {err}")

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
            provider="openrouter",
        )
