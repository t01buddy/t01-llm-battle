import os

import httpx

from .base import BaseProvider, ProviderRequest, ProviderResult, ProviderType
from ..pricing import get_tool_cost, get_tool_functions, load_tool_pricing


class TavilyProvider(BaseProvider):
    name = "tavily"
    display_name = "Tavily"
    provider_type = ProviderType.TOOL

    def models(self) -> list[str]:
        return get_tool_functions(self.name)

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
        tool = load_tool_pricing().get(self.name, {})
        credits_used = tool.get("credits_per_call", 1.0)
        cost_usd = get_tool_cost(self.name)

        return ProviderResult(
            content=content,
            input_tokens=None,
            output_tokens=None,
            credits_used=credits_used,
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
