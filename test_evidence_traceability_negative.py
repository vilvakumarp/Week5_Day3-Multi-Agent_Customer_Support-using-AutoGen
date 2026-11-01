
import asyncio
from unittest import result

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

    question = "What is the complaint resolution timeline?"

    web_findings = [
        {
            "source_title": "Karnataka Bank Complaint Handling SOP",
            "source_url": "https://www.karnatakabank.bank.in/example",
            "retrieval_status": "success",
            "source_content": (
                "General customer complaints must be resolved "
                "within 30 days."
            )
        }
    ]

    # Deliberately provide an incorrect claim.
    proposed_response = (
        "Karnataka Bank must resolve all customer complaints "
        "within 15 days."
    )

    result = await validate_response(
        question=question,
        organisation=organisation,
        proposed_response=proposed_response,
        rag_passages=[],
        web_findings=web_findings
    )

    print("\nNEGATIVE TRACEABILITY TEST")
    print("=" * 60)

    print("Validation status:", result["validation_status"])
    print("Issues:", result["issues"])

    print("\nEvidence References:")

    for reference in result.get("evidence_references", []):
        print(reference)

    # Check that the invented 15-day claim
    # has not been included as verified evidence.
    for reference in result.get("evidence_references", []):
        assert "15 days" not in reference["supporting_passage"]


    print("\nUnsupported Claims:")
    print(result.get("unsupported_claims", []))

    print("\nSupported Claims:")
    print(result.get("supported_claims", []))

    print("\nComplete Result:")
    print(result)

    print("\nSUCCESS: No fabricated 15-day evidence reference found.")


if __name__ == "__main__":
    asyncio.run(run_test())
