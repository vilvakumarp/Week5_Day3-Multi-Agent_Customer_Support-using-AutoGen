
from agents.response_validation_agent import validate_response


def test_wrong_organisation_evidence():

    print("\nRAG WRONG ORGANISATION TEST")
    print("=" * 60)

    # The active organisation is ID 3.
    organisation = {
        "id": 3,
        "name": "Another Bank",
        "industry": "Banking",
        "official_website": "https://www.example-bank.com",
        "regulator": "Reserve Bank of India"
    }

    # This passage belongs to Organisation ID 2.
    rag_passages = [
        {
            "content": "General customer complaints must be resolved within 30 days.",
            "filename": "Customer_Complaint_SOP.pdf",
            "page": 10,
            "organisation_id": 2,
            "document_id": 1,
            "distance": 0.25
        }
    ]

    question = "What is the complaint resolution timeline?"

    proposed_response = (
        "General customer complaints must be resolved within 30 days."
    )

    import asyncio
    result = asyncio.run(validate_response(
        question=question,
        organisation=organisation,
        proposed_response=proposed_response,
        rag_passages=rag_passages,
        web_findings=[]
    ))

    print("Validation Status:", result.get("validation_status"))
    print("\nEvidence References:")

    for reference in result.get("evidence_references", []):
        print(reference)

    print("\nComplete Result:")
    print(result)

    # Evidence from another organisation must not be referenced.
    assert result.get("evidence_references", []) == [], (
        "FAILED: Evidence from another organisation was accepted!"
    )

    print("\nSUCCESS: Wrong-organisation evidence was rejected.")


if __name__ == "__main__":
    test_wrong_organisation_evidence()
