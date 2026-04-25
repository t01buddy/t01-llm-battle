import os
import json

import httpx

from .base import BaseProvider, ProviderRequest, ProviderResult, ProviderType
from ..pricing import get_tool_cost, get_tool_functions, load_tool_pricing

_ENDPOINTS = {
    "search": "https://google.serper.dev/search",
    "news": "https://google.serper.dev/news",
}


class SerperProvider(BaseProvider):
    name = "serper"
    display_name = "Serper.dev"
    provider_type = ProviderType.TOOL

    def models(self) -> list[str]:
        return get_tool_functions(self.name)

    async def run(self, request: ProviderRequest) -> ProviderResult:
        api_key = request.api_key or os.environ.get("SERPER_API_KEY", "")
        function = request.model  # "search" or "news"
        endpoint = _ENDPOINTS.get(function, _ENDPOINTS["search"])

        async with httpx.AsyncClient() as client:
            response = await client.post(
                endpoint,
                json={"q": request.user_prompt},
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        content = _format_serper_results(data, function)
        tool = load_tool_pricing().get(self.name, {})
        credits_used = tool.get("credits_per_call", 1.0)
        cost_usd = get_tool_cost(self.name)

        return ProviderResult(
            content=content,
            input_tokens=None,
            output_tokens=None,
            credits_used=credits_used,
            cost_usd=cost_usd,
            model=function,
            provider="serper",
        )


def _format_serper_results(data: dict, function: str) -> str:
    lines = []
    if function == "news":
        for item in data.get("news", []):
            lines.append(f"**{item.get('title', '')}**")
            lines.append(item.get("snippet", ""))
            lines.append(f"Source: {item.get('link', '')}")
            lines.append("")
    else:
        for item in data.get("organic", []):
            lines.append(f"**{item.get('title', '')}**")
            lines.append(item.get("snippet", ""))
            lines.append(f"URL: {item.get('link', '')}")
            lines.append("")

    if not lines:
        lines.append(json.dumps(data, indent=2))

    return "\n".join(lines).strip()
