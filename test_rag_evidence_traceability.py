
import asyncio

from agents.response_validation_agent import validate_response


async def run_test():

    organisation = {
        "id": 2,
        "name": "Karnataka Bank",
        "industry": "Banking",
        "institution_category": "Scheduled Commercial Bank",
        "bank_category": "Private Sector Bank",
        "regulator": "Reserve Bank of India"
    }

    # Simulated RAG result using the actual retrieval.py structure.
    rag_passages = [
        {
            "content": (
                "General customer complaints must be resolved "
                "within 30 days."
            ),
            "filename": "Customer_Complaint_SOP.pdf",
            "page": 10,
            "organisation_id": 2,
            "document_id": 1,
            "distance": 0.25
        }
    ]

    question = "What is the complaint resolution timeline?"

    proposed_response = (
        "General customer complaints must be resolved "
        "within 30 days."
    )

    result = await validate_response(
        question=question,
        organisation=organisation,
        proposed_response=proposed_response,
        rag_passages=rag_passages,
        web_findings=[]
    )

    print("\nRAG EVIDENCE TRACEABILITY TEST")
    print("=" * 60)

    print("Status:", result["validation_status"])

    print("\nEvidence References:")

    for reference in result.get("evidence_references", []):
        print(reference)

    print("\nComplete Result:")
    print(result)

    # Verify RAG reference.
    rag_references = [
        ref for ref in result.get("evidence_references", [])
        if ref.get("source_type") == "rag"
    ]

    assert len(rag_references) > 0, (
        "No verified RAG evidence reference was generated."
    )

    assert rag_references[0]["source_name"] == (
        "Customer_Complaint_SOP.pdf"
    )

    assert rag_references[0]["page"] == 10

    print("\nSUCCESS: RAG evidence traceability verified.")


if __name__ == "__main__":
    asyncio.run(run_test())
