import pytest
from agents.response_validation_agent import validate_response


@pytest.mark.asyncio
async def test_missing_rag_evidence():

    print("\nRAG MISSING EVIDENCE TEST")
    print("=" * 60)

    # Active organisation: ID 2.
    organisation = {
        "id": 2,
        "name": "Karnataka Bank",
        "industry": "Banking",
        "official_website": "https://www.karnatakabank.bank.in",
        "regulator": "Reserve Bank of India"
    }

    # This passage belongs to the correct organisation,
    # but it does not support the proposed claim.
    rag_passages = [
        {
            "content": "Customers can submit complaints through the bank's branch network.",
            "filename": "Customer_Complaint_SOP.pdf",
            "page": 5,
            "organisation_id": 2,
            "document_id": 1,
            "distance": 0.25
        }
    ]

    question = "How many days does the bank take to resolve complaints?"

    proposed_response = (
        "General customer complaints must be resolved within 30 days."
    )

    result = await validate_response(
        question=question,
        organisation=organisation,
        proposed_response=proposed_response,
        rag_passages=rag_passages,
        web_findings=[]
    )

    print("Validation Status:", result.get("validation_status"))
    print("\nEvidence References:")

    for reference in result.get("evidence_references", []):
        print(reference)

    print("\nComplete Result:")
    print(result)

    # The unrelated passage must not be used as evidence.
    assert result.get("evidence_references", []) == [], (
        "FAILED: An unrelated RAG passage was accepted as evidence!"
    )

    print("\nSUCCESS: Unsupported RAG evidence was rejected.")


import asyncio

if __name__ == "__main__":
    asyncio.run(test_missing_rag_evidence())
