
import asyncio
import json

from database.db_manager import init_db, get_connection
from rag.retrieval import search_knowledge_base

from agents.response_validation_agent import validate_response


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


async def run_test(
    test_name,
    question,
    proposed_response,
    organisation,
    passages
):

    print("\n" + "=" * 70)
    print(test_name)
    print("=" * 70)

    result = await validate_response(
        question=question,
        organisation=organisation,
        proposed_response=proposed_response,
        rag_passages=passages,
        web_findings=[]
    )

    print("\nVALIDATION RESULT")
    print(json.dumps(
        result,
        indent=4,
        ensure_ascii=False
    ))

    print("\nSTATUS:", result.get("validation_status"))
    print("CONFIDENCE:", result.get("confidence"))
    print("ISSUES:", result.get("issues"))
    print("CORRECTIONS REQUIRED:", result.get("corrections_required"))

    return result


async def main():

    init_db()

    organisation = load_organisation()

    question = (
        "How many days does Karnataka Bank take to resolve "
        "a general customer complaint?"
    )

    print("Organisation:", organisation["name"])

    print("\nRetrieving RAG evidence...")

    passages = search_knowledge_base(
        question=question,
        organisation_id=organisation["id"],
        top_k=5
    )

    print("Retrieved passages:", len(passages))

    # Test 1: Correct answer.
    await run_test(
        test_name="TEST 1 - Correct answer",
        question=question,
        proposed_response=(
            "According to the supplied Karnataka Bank SOP, "
            "the maximum turnaround time for resolving general "
            "complaints is 30 days, including all three levels: "
            "Branch, Regional Office and Head Office."
        ),
        organisation=organisation,
        passages=passages
    )

    # Test 2: Incorrect turnaround time.
    await run_test(
        test_name="TEST 2 - Incorrect turnaround time",
        question=question,
        proposed_response=(
            "Karnataka Bank resolves all general customer "
            "complaints within 7 days."
        ),
        organisation=organisation,
        passages=passages
    )

    # Test 3: Unsupported claim.
    await run_test(
        test_name="TEST 3 - Unsupported claim",
        question=(
            "Does Karnataka Bank guarantee compensation "
            "of Rs. 10,000 for every delayed complaint?"
        ),
        proposed_response=(
            "Yes. Karnataka Bank guarantees Rs. 10,000 "
            "compensation for every delayed complaint."
        ),
        organisation=organisation,
        passages=passages
    )


if __name__ == "__main__":
    asyncio.run(main())
