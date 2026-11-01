
import asyncio
import json

from database.db_manager import init_db, get_connection

from agents.query_understanding_agent import understand_query


def load_organisation_context():

    with get_connection() as conn:

        row = conn.execute("""
            SELECT
                o.id,
                o.name,
                o.domain,
                o.official_website,
                o.metadata_json
            FROM organisations o
            ORDER BY o.id DESC
            LIMIT 1
        """).fetchone()

    if not row:
        raise ValueError("No organisation found in SQLite.")

    metadata = json.loads(row["metadata_json"] or "{}")

    return {
        "id": row["id"],
        "name": row["name"],
        "industry": row["domain"],
        "official_website": row["official_website"],
        "topics": metadata.get("topics", []),
        "document_category": metadata.get("document_category"),
        "research_scope": metadata.get("research_scope")
    }


async def main():

    init_db()

    organisation_context = load_organisation_context()

    print("\nORGANISATION CONTEXT")
    print(json.dumps(organisation_context, indent=4))

    test_questions = [

        "How many days does the bank take to resolve a customer complaint?",

        "What is the process for escalating an unresolved complaint?",

        "What are the latest RBI guidelines for customer grievance redressal?",

        "What is the current interest rate for Karnataka Bank savings accounts?"
    ]

    for index, question in enumerate(test_questions, start=1):

        print("\n" + "=" * 70)
        print(f"TEST QUESTION {index}")
        print("=" * 70)

        print("Customer:", question)

        result = await understand_query(
            question=question,
            organisation_context=organisation_context
        )

        print("\nQUERY UNDERSTANDING RESULT")
        print(json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        ))

        print("\nROUTING DECISION")
        print("Intent:", result.get("intent"))
        print("Topic:", result.get("topic"))
        print("RAG required:", result.get("requires_rag"))
        print("Web research required:", result.get("requires_web_research"))
        print("Current information:", result.get("requires_current_information"))
        print("Research scope:", result.get("research_scope"))


if __name__ == "__main__":
    asyncio.run(main())
