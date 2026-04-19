from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class ProviderType(Enum):
    LLM = "llm"    # Pydantic AI backed; token-based pricing
    TOOL = "tool"   # plain httpx; credit-based pricing


@dataclass
class TokenPricing:
    input_per_million: float   # USD per 1M input tokens
    output_per_million: float  # USD per 1M output tokens


@dataclass
class CreditPricing:
    credits_per_call: float    # credits consumed per call
    usd_per_credit: float      # USD per credit


@dataclass
class ProviderRequest:
    model: str                 # model slug (LLM) or function name (TOOL)
    system_prompt: str | None
    user_prompt: str
    temperature: float = 0.7
    max_tokens: int = 2048
    extra: dict = field(default_factory=dict)


@dataclass
class ProviderResult:
    content: str
    input_tokens: int | None   # None for TOOL providers
    output_tokens: int | None  # None for TOOL providers
    credits_used: float | None  # None for LLM providers
    cost_usd: float | None
    model: str
    provider: str
    error: str | None = None


class BaseProvider(ABC):
    """Abstract base class for all provider adapters."""

    name: str
    display_name: str
    provider_type: ProviderType

    @abstractmethod
    async def run(self, request: ProviderRequest) -> ProviderResult:
        ...

    @abstractmethod
    def models(self) -> list[str]:
        ...

    def cost(self, result: ProviderResult) -> float | None:
        return result.cost_usd


# Backward-compatible aliases for user plugins that may import old names
CompletionRequest = ProviderRequest
CompletionResult = ProviderResult
