
import os
import requests

from urllib.parse import urlparse
from dotenv import load_dotenv
from datetime import datetime

from database.search_cache import (
    generate_cache_key,
    get_cached_results,
    store_cached_results
)


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY")

SERPER_URL = "https://google.serper.dev/search"

DEFAULT_RESULTS = 10


# ============================================================
# CONTEXT-AWARE QUERY BUILDER
# ============================================================

def build_search_query(
    organisation_name,
    question,
    topics=None,
    official_website=None,
    research_scope="organisation"
):
    if not organisation_name:
        raise ValueError("Organisation name is required.")

    if not question:
        raise ValueError("Question is required.")

    topic_text = ""

    if topics:
        topic_text = " ".join(topics[:4])

    question_lower = question.lower()

    # Detect whether the user wants recent information.
    freshness_keywords = [
        "latest",
        "current",
        "recent",
        "new",
        "updated",
        "today",
        "as of"
    ]

    requires_freshness = any(
        keyword in question_lower
        for keyword in freshness_keywords
    )

    current_year = datetime.now().year

    # --------------------------------------------------------
    # REGULATORY RESEARCH
    # --------------------------------------------------------

    if research_scope == "regulatory":

        # RBI-specific regulatory research.
        if "rbi" in question_lower or "reserve bank" in question_lower:

            search_query = (
                f'site:rbi.org.in '
                f'{question} '
                f'{topic_text} '
                f'circular notification "master direction"'
            )

            if requires_freshness:
                search_query += (
                    f' ({current_year} OR {current_year - 1})'
                )

        else:
            # Other regulatory research.
            search_query = (
                f'{question} '
                f'{organisation_name} '
                f'{topic_text} '
                f'regulatory circular notification guidelines'
            )

            if requires_freshness:
                search_query += (
                    f' {current_year} {current_year - 1}'
                )

    # --------------------------------------------------------
    # ORGANISATION-SPECIFIC RESEARCH
    # --------------------------------------------------------

    else:

        search_query = (
            f'"{organisation_name}" '
            f'{question} '
            f'{topic_text}'
        )

        if requires_freshness:
            search_query += (
                f' {current_year} {current_year - 1}'
            )

    return " ".join(search_query.split())



# ============================================================
# SERPER API REQUEST
# ============================================================

def call_serper(search_query, num_results=DEFAULT_RESULTS):
    """
    Execute a Google search through Serper.dev.
    """

    if not SERPER_API_KEY:
        raise ValueError(
            "SERPER_API_KEY is missing from the .env file."
        )

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "q": search_query,
        "num": num_results
    }

    response = requests.post(
        SERPER_URL,
        headers=headers,
        json=payload,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    organic_results = []

    for item in data.get("organic", []):

        organic_results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "date": item.get("date", ""),
            "position": item.get("position")
        })

    return {
        "search_query": search_query,
        "organic_results": organic_results,
        "total_results_returned": len(organic_results),
        "search_provider": "Serper.dev"
    }


# ============================================================
# CONTEXT-AWARE SEARCH WITH CACHE
# ============================================================

def search_web(
    organisation_id,
    organisation_name,
    question,
    topics=None,
    official_website=None,
    research_scope="organisation",
    conversation_id=None,
    cache_hours=24,
    force_refresh=False
):
    """
    Perform organisation-aware web research.

    1. Build contextual query.
    2. Check SQLite cache.
    3. Return cached results if valid.
    4. Otherwise call Serper.dev.
    5. Store results in SQLite.
    """

    search_query = build_search_query(
        organisation_name=organisation_name,
        question=question,
        topics=topics,
        official_website=official_website,
        research_scope=research_scope
    )

    cache_key = generate_cache_key(
        organisation_id=organisation_id,
        search_query=search_query,
        research_scope=research_scope
    )

    # --------------------------------------------------------
    # 1. Check existing cache
    # --------------------------------------------------------

    if not force_refresh:

        cached = get_cached_results(cache_key)

        if cached:

            return {
                "status": "cache_hit",
                "search_query": search_query,
                "results": cached["results"],
                "cached_at": cached["created_at"],
                "expires_at": cached["expires_at"]
            }

    # --------------------------------------------------------
    # 2. Perform fresh search
    # --------------------------------------------------------

    search_results = call_serper(
        search_query=search_query
    )

    # --------------------------------------------------------
    # 3. Store research in SQLite
    # --------------------------------------------------------

    store_cached_results(
        cache_key=cache_key,
        search_query=search_query,
        results=search_results,
        organisation_id=organisation_id,
        conversation_id=conversation_id,
        topic=question,
        cache_hours=cache_hours
    )

    return {
        "status": "fresh_search",
        "search_query": search_query,
        "results": search_results
    }
