
import asyncio
import json

from database.db_manager import init_db, get_connection
from rag.retrieval import search_knowledge_base

from agents.response_generation_agent import generate_response


def load_organisation():

    with get_connection() as conn:

        row = conn.execute("""
            SELECT id, name, domain, official_website
            FROM organisations
            WHERE name = ?
            LIMIT 1
        """, ("Karnataka Bank",)).fetchone()

    if not row:
        raise ValueError("Karnataka Bank not found in SQLite.")

    return {
        "id": row["id"],
        "name": row["name"],
        "industry": row["domain"],
        "official_website": row["official_website"]
    }


async def main():

    init_db()

    organisation = load_organisation()

    question = (
        "How many days does Karnataka Bank take to resolve "
        "a general customer complaint?"
    )

    print("\n1. ORGANISATION")
    print(organisation["name"])

    print("\n2. RETRIEVING RAG EVIDENCE")

    passages = search_knowledge_base(
        question=question,
        organisation_id=organisation["id"],
        top_k=5
    )

    print("Retrieved passages:", len(passages))

    for index, passage in enumerate(passages, start=1):

        print(f"\nPassage {index}")
        print("Filename:", passage.get("filename"))
        print("Page:", passage.get("page"))
        print("Content:", passage.get("content", "")[:250])

    # This first test uses RAG only.
    # Web findings will be added in the orchestration stage.

    web_findings = []

    print("\n3. STARTING RESPONSE GENERATION AGENT")

    result = await generate_response(
        question=question,
        organisation=organisation,
        rag_passages=passages,
        web_findings=web_findings
    )

    print("\n4. GENERATED RESPONSE")
    print("=" * 65)

    print(json.dumps(
        result,
        indent=4,
        ensure_ascii=False
    ))

    print("\n5. CUSTOMER-FACING ANSWER")
    print("=" * 65)

    print(result.get("answer"))

    print("\nAnswer status:", result.get("answer_status"))

    print("\nSources:")

    for source in result.get("sources", []):

        print("-", source.get("source_name"))

        if source.get("page"):
            print("  Page:", source.get("page"))

        if source.get("url"):
            print("  URL:", source.get("url"))

    print("\nLimitations:", result.get("limitations", []))


if __name__ == "__main__":
    asyncio.run(main())
