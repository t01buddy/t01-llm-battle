import httpx

from .base import BaseProvider, CompletionRequest, CompletionResult

_DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider(BaseProvider):
    name = "ollama"

    def __init__(self, base_url: str = _DEFAULT_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def models(self) -> list[str]:
        """Query Ollama's /api/tags for installed models; return [] if not running."""
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            if response.status_code != 200:
                return []
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Ollama is local and free — always 0.0."""
        return 0.0

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.user_prompt})

        payload = {
            "model": request.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )

        if response.status_code != 200:
            try:
                err = response.json().get("error", response.text)
            except Exception:
                err = response.text
            raise RuntimeError(f"Ollama API error {response.status_code}: {err}")

        data = response.json()
        content = data["message"]["content"]
        input_tokens = data.get("prompt_eval_count", 0)
        output_tokens = data.get("eval_count", 0)

        return CompletionResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0.0,
            model=request.model,
            provider="ollama",
        )
