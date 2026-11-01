
import sqlite3
import json

from pathlib import Path

from tools.web_search import search_web


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "chat_history.db"


def get_test_context():

    with sqlite3.connect(DB_PATH) as conn:

        conn.row_factory = sqlite3.Row

        document = conn.execute(
            """
            SELECT *
            FROM documents
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if document is None:
            raise ValueError("No registered documents found.")

        organisation = conn.execute(
            """
            SELECT *
            FROM organisations
            WHERE id = ?
            """,
            (document["organisation_id"],)
        ).fetchone()

        if organisation is None:
            raise ValueError("Organisation not found.")

    document_metadata = json.loads(
        document["metadata_json"] or "{}"
    )

    return {
        "organisation_id": organisation["id"],
        "organisation_name": organisation["name"],
        "official_website": organisation["official_website"],
        "topics": document_metadata.get("topics", [])
    }


def display_results(result):

    print("\nSearch status:", result["status"])
    print("Search query:", result["search_query"])

    search_data = result["results"]

    organic_results = search_data.get(
        "organic_results", []
    )

    print("\nNumber of results:", len(organic_results))

    for index, item in enumerate(
        organic_results[:5], start=1
    ):

        print(f"\nRESULT {index}")
        print("Title:", item["title"])
        print("URL:", item["url"])
        print("Snippet:", item["snippet"])


def run_cache_test(context, question, research_scope):

    print("\n" + "=" * 70)
    print(f"RESEARCH SCOPE: {research_scope.upper()}")
    print("=" * 70)

    print("\nQuestion:", question)

    # First search: force a fresh Serper request.
    print("\n1. Performing fresh search...")

    first_result = search_web(
        organisation_id=context["organisation_id"],
        organisation_name=context["organisation_name"],
        question=question,
        topics=context["topics"],
        official_website=context["official_website"],
        research_scope=research_scope,
        cache_hours=24,
        force_refresh=True
    )

    display_results(first_result)

    # Second search: should use SQLite cache.
    print("\n2. Repeating the same search...")

    second_result = search_web(
        organisation_id=context["organisation_id"],
        organisation_name=context["organisation_name"],
        question=question,
        topics=context["topics"],
        official_website=context["official_website"],
        research_scope=research_scope,
        cache_hours=24,
        force_refresh=False
    )

    display_results(second_result)

    # Verify cache behaviour.
    print("\n3. CACHE VERIFICATION")

    if (
        first_result["status"] == "fresh_search"
        and second_result["status"] == "cache_hit"
    ):

        print("SUCCESS: Search caching is working.")
        print("First request: Serper.dev")
        print("Second request: SQLite cache")

    else:

        print("WARNING: Expected cache behaviour was not observed.")

    return first_result, second_result


def main():

    print("\n1. Loading organisation context...")

    context = get_test_context()

    print("Organisation:", context["organisation_name"])
    print("Organisation ID:", context["organisation_id"])
    print("Topics:", context["topics"])

    # --------------------------------------------------------
    # TEST A: ORGANISATION-SPECIFIC RESEARCH
    # --------------------------------------------------------

    organisation_question = (
        "What are the complaint escalation procedures "
        "and turnaround time requirements?"
    )

    run_cache_test(
        context=context,
        question=organisation_question,
        research_scope="organisation"
    )

    # --------------------------------------------------------
    # TEST B: REGULATORY RESEARCH
    # --------------------------------------------------------

    regulatory_question = (
        "What are the latest RBI guidelines "
        "for customer grievance redressal?"
    )

    run_cache_test(
        context=context,
        question=regulatory_question,
        research_scope="regulatory"
    )

    print("\n" + "=" * 70)
    print("ALL WEB RESEARCH TESTS COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    main()
