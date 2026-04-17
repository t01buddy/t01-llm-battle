from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CompletionRequest:
    model: str
    system_prompt: str
    user_prompt: str
    temperature: float = 0.7
    max_tokens: int = 2048


@dataclass
class CompletionResult:
    content: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str
    provider: str
    error: str | None = None


class BaseProvider(ABC):
    """Abstract base class for all LLM provider adapters."""

    name: str  # e.g. "openai", "anthropic"

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """Send a completion request and return the result."""
        ...

    @abstractmethod
    def models(self) -> list[str]:
        """Return list of supported model IDs."""
        ...

    def cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate cost in USD. Override per provider with real pricing."""
        return 0.0
