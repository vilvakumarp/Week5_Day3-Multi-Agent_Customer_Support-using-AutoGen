
import hashlib
import json
from datetime import datetime, timedelta, timezone

from database.db_manager import (
    get_cached_research,
    save_research
)


# ============================================================
# CACHE CONFIGURATION
# ============================================================

DEFAULT_CACHE_HOURS = 24


def generate_cache_key(
    organisation_id,
    search_query,
    research_scope="organisation"
):
    """
    Generate a deterministic cache key.

    Different organisations and research scopes
    must never share cached results.
    """

    normalized_query = " ".join(
        search_query.lower().split()
    )

    cache_data = {
        "organisation_id": organisation_id,
        "query": normalized_query,
        "research_scope": research_scope
    }

    raw = json.dumps(
        cache_data,
        sort_keys=True
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# CACHE RETRIEVAL
# ============================================================

def get_cached_results(cache_key):
    """
    Return valid cached research or None.
    """

    cached = get_cached_research(cache_key)

    if cached is None:
        return None

    return cached


# ============================================================
# CACHE STORAGE
# ============================================================

def store_cached_results(
    cache_key,
    search_query,
    results,
    organisation_id,
    conversation_id=None,
    topic=None,
    cache_hours=DEFAULT_CACHE_HOURS
):
    """
    Store search results with an expiry timestamp.
    """

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(hours=cache_hours)
    ).isoformat()

    return save_research(
        cache_key=cache_key,
        search_query=search_query,
        results=results,
        organisation_id=organisation_id,
        conversation_id=conversation_id,
        topic=topic,
        expires_at=expires_at
    )
