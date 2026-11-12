"""
Wikipedia search tool implementation.

This tool searches Wikipedia for general information including medical topics.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from server.chat.streaming.response import (
    end_message,
    status_message,
)
from server.chat.tools._helpers import parse_tool_args
from server.chat.tools.sanitization import sanitize_query_for_external_search

logger = logging.getLogger(__name__)

WIKIPEDIA_API_BASE = "https://en.wikipedia.org/w/api.php"


async def search_wikipedia(
    query: str, max_results: int = 3, patient_context: dict | None = None
) -> list[dict]:
    # Pass patient_context down to the sanitizer
    query = sanitize_query_for_external_search(query, patient_context=patient_context)

    # Pre-flight request abatement: Do NOT make an outbound network call if query is empty
    if not query:
        logger.info(
            "Search query scrubbed completely; aborting outbound Wikipedia request."
        )
        return []

    headers = {
        "User-Agent": "PhloxMedicalBot/1.0 (https://github.com/phlox-medical; bot@phlox.example)"
    }

    async with httpx.AsyncClient() as client:
        search_response = await client.get(
            WIKIPEDIA_API_BASE,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": min(max_results, 10),
                "format": "json",
            },
            headers=headers,
        )
        search_data = search_response.json()
        search_results = search_data.get("query", {}).get("search", [])

        if not search_results:
            return []

        titles = [result["title"] for result in search_results[:max_results]]
        extracts_response = await client.get(
            WIKIPEDIA_API_BASE,
            params={
                "action": "query",
                "prop": "extracts",
                "exintro": True,
                "explaintext": True,
                "exsentences": 5,
                "titles": "|".join(titles),
                "format": "json",
            },
            headers=headers,
        )
        extracts_data = extracts_response.json()
        pages = extracts_data.get("query", {}).get("pages", {})

        articles = []
        for result in search_results[:max_results]:
            page_id = str(result["pageid"])
            page_data = pages.get(page_id, {})
            articles.append(
                {
                    "title": result["title"],
                    "extract": page_data.get("extract", ""),
                    "url": f"https://en.wikipedia.org/wiki?curid={page_id}",
                }
            )

        return articles


async def execute(
    tool_call: dict[str, Any],
    _llm_client,
    _config: dict[str, Any],
    _message_list: list,
    _context_question_options: dict[str, Any],
) -> AsyncGenerator[dict[str, Any], None]:
    logger.info("Executing web_search (Wikipedia) tool...")
    yield status_message("Searching Wikipedia...")

    function_arguments = parse_tool_args(tool_call)
    query = function_arguments.get("query", "")
    max_results = function_arguments.get("max_results", 3)

    # Extract patient context from configuration or runtime options if available
    patient_context = _config.get("patient_context") or _context_question_options.get(
        "patient_context"
    )

    # Sanitize query using active context
    query = sanitize_query_for_external_search(query, patient_context=patient_context)

    citations: list[dict] = []
    result_content: str = ""

    if not query:
        logger.info("No valid query remaining after sanitization; aborting web search.")
        result_content = (
            "Query contained only protected information or was empty. Search aborted."
        )
    else:
        try:
            articles = await search_wikipedia(
                query, max_results, patient_context=patient_context
            )
            if not articles:
                result_content = f"No Wikipedia articles found for query: '{query}'"
            else:
                formatted = [
                    f"[{i + 1}] Title: {art['title']}\nSummary: {art.get('extract', '')}\nURL: {art['url']}"
                    for i, art in enumerate(articles)
                ]
                citations = [
                    {
                        "type": "wiki",
                        "title": art["title"],
                        "url": art["url"],
                        "snippet": art.get("extract", ""),
                    }
                    for art in articles
                ]
                result_content = (
                    "Found the following relevant articles:\n\n"
                    + "\n\n---\n\n".join(formatted)
                )
        except Exception as e:
            logger.error(f"Wikipedia search error: {e}")
            result_content = f"Error searching Wikipedia: {str(e)}"

    yield end_message(
        function_response={"content": result_content, "citations": citations}
    )
