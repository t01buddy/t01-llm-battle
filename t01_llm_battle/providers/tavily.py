import os

import httpx

from .base import BaseProvider, CreditPricing, ProviderRequest, ProviderResult, ProviderType

_PRICING = CreditPricing(credits_per_call=1.0, usd_per_credit=0.002)


class TavilyProvider(BaseProvider):
    name = "tavily"
    display_name = "Tavily"
    provider_type = ProviderType.TOOL

    def models(self) -> list[str]:
        return ["search"]

    async def run(self, request: ProviderRequest) -> ProviderResult:
        api_key = os.environ.get("TAVILY_API_KEY", "")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={"query": request.user_prompt, "api_key": api_key},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        content = _format_tavily_results(data)
        cost_usd = _PRICING.credits_per_call * _PRICING.usd_per_credit

        return ProviderResult(
            content=content,
            input_tokens=None,
            output_tokens=None,
            credits_used=_PRICING.credits_per_call,
            cost_usd=cost_usd,
            model="search",
            provider="tavily",
        )


def _format_tavily_results(data: dict) -> str:
    lines = []
    answer = data.get("answer")
    if answer:
        lines.append(f"**Answer**: {answer}")
        lines.append("")

    for item in data.get("results", []):
        lines.append(f"**{item.get('title', '')}**")
        lines.append(item.get("content", ""))
        lines.append(f"URL: {item.get('url', '')}")
        lines.append("")

    return "\n".join(lines).strip()
