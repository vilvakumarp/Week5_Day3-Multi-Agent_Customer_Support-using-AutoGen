
import asyncio
import json

from database.db_manager import init_db, get_connection
from agents.web_research_agent import run_web_research_agent


async def main():

    init_db()

    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                o.id,
                o.name,
                o.official_website,
                d.metadata_json
            FROM organisations o
            JOIN documents d
                ON d.organisation_id = o.id
            WHERE o.id = 2
            ORDER BY d.id DESC
            LIMIT 1
        """).fetchone()

    if not row:
        print("Organisation or document not found.")
        return

    organisation = {
        "id": row["id"],
        "name": row["name"],
        "official_website": row["official_website"]
    }

    metadata = json.loads(row["metadata_json"] or "{}")

    print("\nStarting Web Research Agent...")
    print("=" * 60)

    result = await run_web_research_agent(
        question="What are the complaint escalation procedures and turnaround time requirements?",
        organisation=organisation,
        document_metadata=metadata,
        rag_passages=[],
        research_scope="organisation",
        must_research=True
    )
    print("\nFULL AGENT RESPONSE")
    print("=" * 60)

    print(json.dumps(
        result,
        indent=4,
        ensure_ascii=False,
        default=str
    ))
    print("\nRESEARCH FINDINGS")
    print("=" * 60)

    for finding in result.get("research_findings", []):

        print("\nTitle:", finding.get("source_title"))
        print("URL:", finding.get("source_url"))
        print("Retrieval:", finding.get("retrieval_status"))

        content = finding.get("source_content", "")

        print("Extracted characters:", len(content))
        print("Content preview:", content[:500])

    print("\nRETRIEVAL SUMMARY")
    print(json.dumps(
        result.get("retrieved_sources", []),
        indent=4,
        ensure_ascii=False
    ))


if __name__ == "__main__":
    asyncio.run(main())
