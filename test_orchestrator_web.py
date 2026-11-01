
import asyncio
import json

from database.db_manager import init_db, get_connection
from orchestrator import run_customer_support


def get_test_organisation():

    with get_connection() as conn:

        row = conn.execute("""
            SELECT
                id,
                name,
                domain,
                official_website,
                metadata_json
            FROM organisations
            WHERE name = ?
            LIMIT 1
        """, ("Karnataka Bank",)).fetchone()

    if not row:
        raise ValueError("Karnataka Bank not found.")

    return dict(row)


async def main():

    init_db()

    organisation = get_test_organisation()
    print("\nORGANISATION CONTEXT:")
    print(json.dumps(organisation, indent=4, ensure_ascii=False))

    question = "What are the latest RBI guidelines for customer grievance redressal?"

    result = await run_customer_support(
        question=question,
        organisation_id=organisation["id"]
    )

    print("\nFINAL CUSTOMER RESPONSE")
    print("=" * 65)
    print(result["answer"])

    print("\nROUTING")
    print("RAG:", result["routing"].get("requires_rag"))
    print("Web:", result["routing"].get("requires_web_research"))
    print("Scope:", result["routing"].get("research_scope"))

    print("\nWEB RESEARCH")
    print("Findings:", len(
        result["web_research"].get("research_findings", [])
    ))

    print("\nVALIDATION DETAILS")
    print("=" * 65)

    print(json.dumps(
        result["validation"],
        indent=4,
        ensure_ascii=False,
        default=str
    ))

    print("\nConversation ID:", result["conversation_id"])


if __name__ == "__main__":
    asyncio.run(main())
