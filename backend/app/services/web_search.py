"""Web search service using Tavily API for accounting-related research.

Restricts results to trusted German accounting/tax sources when possible.
Falls back gracefully when no API key is configured.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TAVILY_URL = "https://api.tavily.com/search"

_TRUSTED_DOMAINS = [
    "haufe.de",
    "datev.de",
    "bundesfinanzministerium.de",
    "iww.de",
    "steuertipps.de",
    "gesetze-im-internet.de",
    "bundesanzeiger.de",
    "ihk.de",
    "nwb.de",
    "smartsteuer.de",
]


async def search_accounting(
    query: str,
    *,
    max_results: int = 5,
    search_depth: str = "advanced",
    include_domains: list[str] | None = None,
    topic: str = "general",
) -> dict:
    """Search the web for accounting/tax information.

    Returns a dict with 'results' (list of search hits) and 'answer' (AI summary).
    """
    if not settings.tavily_api_key:
        return {
            "error": "Web-Suche nicht konfiguriert (TAVILY_API_KEY fehlt)",
            "results": [],
        }

    domains = include_domains or _TRUSTED_DOMAINS

    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "search_depth": search_depth,
        "include_domains": domains,
        "max_results": max_results,
        "topic": topic,
        "include_answer": True,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(_TAVILY_URL, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.RequestError as exc:
        logger.error("Tavily request failed: %s", exc)
        return {"error": f"Suchanfrage fehlgeschlagen: {exc}", "results": []}
    except httpx.HTTPStatusError as exc:
        logger.error("Tavily returned %s", exc.response.status_code)
        return {"error": f"Suchfehler (HTTP {exc.response.status_code})", "results": []}

    results = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", "")[:500],
        }
        for r in data.get("results", [])
    ]

    return {
        "answer": data.get("answer", ""),
        "results": results,
        "query": query,
    }
