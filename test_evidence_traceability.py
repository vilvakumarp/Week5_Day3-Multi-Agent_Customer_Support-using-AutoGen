
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

    question = "What is the complaint resolution timeline?"

    web_findings = [
        {
            "source_title": "Karnataka Bank Complaint Handling SOP",
            "source_url": "https://www.karnatakabank.bank.in/example",
            "retrieval_status": "success",
            "source_content": (
                "General customer complaints must be resolved "
                "within 30 days. If a complaint is not resolved "
                "within this period, the customer may escalate "
                "the matter through the applicable grievance "
                "redressal mechanism."
            )
        }
    ]

    proposed_response = (
        "Karnataka Bank's general customer complaints "
        "must be resolved within 30 days."
    )

    result = await validate_response(
        question=question,
        organisation=organisation,
        proposed_response=proposed_response,
        rag_passages=[],
        web_findings=web_findings
    )

    print("\nVALIDATION RESULT")
    print("=" * 60)

    print("Status:", result["validation_status"])

    print("\nEvidence References:")
    for reference in result.get("evidence_references", []):
        print("Claim:", reference.get("claim"))
        print("Source:", reference.get("source_title"))
        print("URL:", reference.get("source_url"))
        print("Passage:", reference.get("supporting_passage"))
        print("-" * 50)

    print("\nComplete Result:")
    print(result)


if __name__ == "__main__":
    asyncio.run(run_test())
