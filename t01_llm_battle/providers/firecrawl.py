import os

import httpx

from .base import BaseProvider, CreditPricing, ProviderRequest, ProviderResult, ProviderType

_PRICING = CreditPricing(credits_per_call=1.0, usd_per_credit=0.001)


class FirecrawlProvider(BaseProvider):
    name = "firecrawl"
    display_name = "Firecrawl"
    provider_type = ProviderType.TOOL

    def models(self) -> list[str]:
        return ["scrape", "crawl"]

    async def run(self, request: ProviderRequest) -> ProviderResult:
        api_key = os.environ.get("FIRECRAWL_API_KEY", "")
        function = request.model  # "scrape" or "crawl"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient() as client:
            if function == "crawl":
                response = await client.post(
                    "https://api.firecrawl.dev/v1/crawl",
                    json={"url": request.user_prompt},
                    headers=headers,
                    timeout=60.0,
                )
            else:
                response = await client.post(
                    "https://api.firecrawl.dev/v1/scrape",
                    json={"url": request.user_prompt},
                    headers=headers,
                    timeout=30.0,
                )
            response.raise_for_status()
            data = response.json()

        content = _format_firecrawl_results(data, function)
        cost_usd = _PRICING.credits_per_call * _PRICING.usd_per_credit

        return ProviderResult(
            content=content,
            input_tokens=None,
            output_tokens=None,
            credits_used=_PRICING.credits_per_call,
            cost_usd=cost_usd,
            model=function,
            provider="firecrawl",
        )


def _format_firecrawl_results(data: dict, function: str) -> str:
    if function == "crawl":
        pages = data.get("data", [])
        lines = [f"Crawled {len(pages)} page(s):", ""]
        for page in pages:
            lines.append(f"**{page.get('metadata', {}).get('title', page.get('url', ''))}**")
            lines.append(page.get("markdown", page.get("content", ""))[:500])
            lines.append("")
        return "\n".join(lines).strip()

    # scrape
    page = data.get("data", data)
    markdown = page.get("markdown", page.get("content", ""))
    title = page.get("metadata", {}).get("title", "")
    lines = []
    if title:
        lines.append(f"**{title}**")
        lines.append("")
    lines.append(markdown)
    return "\n".join(lines).strip()
