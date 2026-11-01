
import asyncio
import json

from database.db_manager import get_connection, init_db

from rag.retrieval import search_knowledge_base

from agents.web_research_agent import run_web_research_agent


def load_latest_document_context():

    with get_connection() as conn:

        row = conn.execute("""
            SELECT
                o.id AS organisation_id,
                o.name AS organisation_name,
                o.domain,
                o.official_website,
                d.id AS document_id,
                d.filename,
                d.metadata_json
            FROM documents d
            JOIN organisations o
                ON d.organisation_id = o.id
            ORDER BY d.uploaded_at DESC
            LIMIT 1
        """).fetchone()

    if not row:
        raise ValueError("No registered document found in SQLite.")

    metadata = json.loads(row["metadata_json"] or "{}")

    organisation = {
        "id": row["organisation_id"],
        "name": row["organisation_name"],
        "domain": row["domain"],
        "official_website": row["official_website"]
    }

    document_metadata = {
        "document_id": row["document_id"],
        "filename": row["filename"],
        **metadata
    }

    return organisation, document_metadata


async def main():

    init_db()

    print("\n1. Loading organisation and document context...")

    organisation, document_metadata = load_latest_document_context()

    print("Organisation:", organisation["name"])
    print("Organisation ID:", organisation["id"])
    print("Document:", document_metadata["filename"])
    print("Topics:", document_metadata.get("topics", []))

    question = (
        "What is the procedure for escalating customer complaints "
        "and what are the applicable turnaround times?"
    )

    print("\n2. Retrieving information from ChromaDB...")

    passages = search_knowledge_base(
        question=question,
        organisation_id=organisation["id"],
        top_k=5
    )

    print("RAG passages retrieved:", len(passages))

    for index, passage in enumerate(passages, start=1):

        print(f"\nRAG PASSAGE {index}")
        print("Page:", passage.get("page"))
        print("Content:", passage.get("content", "")[:400])

    print("\n3. Starting AutoGen Web Research Agent...")

    result = await run_web_research_agent(
        question=question,
        organisation=organisation,
        document_metadata=document_metadata,
        rag_passages=passages
    )

    print("\n4. RESEARCH AGENT RESPONSE")
    print("=" * 65)

    print(json.dumps(
        result,
        indent=4,
        ensure_ascii=False
    ))

    print("\n5. RESEARCH SUMMARY")
    print("=" * 65)

    print("Research required:", result.get("research_required"))
    print("Reason:", result.get("reason"))
    print("Summary:", result.get("summary"))

    findings = result.get("research_findings", [])

    print("\nNumber of research findings:", len(findings))

    for index, finding in enumerate(findings, start=1):

        print(f"\nFinding {index}")
        print("Details:", finding.get("finding"))
        print("Source:", finding.get("source_title"))
        print("URL:", finding.get("source_url"))


if __name__ == "__main__":
    asyncio.run(main())
