
import asyncio
import json

from database.db_manager import (
    init_db,
    get_connection,
    get_conversation_messages
)

from orchestrator import run_customer_support


def get_test_organisation():

    with get_connection() as conn:

        row = conn.execute("""
            SELECT id, name
            FROM organisations
            WHERE name = ?
            LIMIT 1
        """, ("Karnataka Bank",)).fetchone()

    if not row:
        raise ValueError("Karnataka Bank not found in database.")

    return dict(row)


async def main():

    init_db()

    organisation = get_test_organisation()

    print("\nCUSTOMER SUPPORT END-TO-END TEST")
    print("=" * 65)

    print("Organisation:", organisation["name"])

    # First test: RAG-only question.
    question = (
        "How many days does Karnataka Bank take to resolve "
        "a general customer complaint?"
    )

    result = await run_customer_support(
        question=question,
        organisation_id=organisation["id"]
    )

    print("\n" + "=" * 65)
    print("FINAL CUSTOMER RESPONSE")
    print("=" * 65)

    print(result["answer"])

    print("\nAnswer status:", result["answer_status"])

    print("\nConversation ID:", result["conversation_id"])

    # Verify conversation persistence.
    print("\nVERIFYING SQLITE CONVERSATION HISTORY")
    print("=" * 65)

    messages = get_conversation_messages(
        result["conversation_id"]
    )

    for message in messages:

        print("\nRole:", message["role"])
        print("Agent:", message.get("agent_name"))
        print("Message:", message["content"][:500])

    # Verify agent activity persistence.
    with get_connection() as conn:

        activities = conn.execute("""
            SELECT
                agent_name,
                activity_type,
                status
            FROM agent_activity
            WHERE conversation_id = ?
            ORDER BY id
        """, (result["conversation_id"],)).fetchall()

    print("\nAGENT ACTIVITY HISTORY")
    print("=" * 65)

    for activity in activities:
        print(
            activity["agent_name"],
            "|",
            activity["activity_type"],
            "|",
            activity["status"]
        )

    print("\nEND-TO-END TEST COMPLETED")


if __name__ == "__main__":
    asyncio.run(main())
