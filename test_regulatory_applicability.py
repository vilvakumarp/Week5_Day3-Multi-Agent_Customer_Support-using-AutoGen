
import asyncio

from agents.response_validation_agent import validate_response


organisation = {
    "id": 2,
    "name": "Karnataka Bank",
    "industry": "Banking",
    "organisation_type": "Bank",
    "institution_category": "Scheduled Commercial Bank",
    "bank_category": "Private Sector Bank",
    "regulator": "Reserve Bank of India"
}


async def run_test():

    question = (
        "Does the latest RBI Internal Ombudsman direction "
        "for Small Finance Banks apply to Karnataka Bank?"
    )

    web_findings = [
        {
            "source_title": "RBI Internal Ombudsman Directions 2026",
            "source_url": "https://www.rbi.org.in/example",
            "retrieval_status": "success",
            "source_content": (
                "These directions apply to Small Finance Banks "
                "meeting the specified eligibility criteria. "
                "They do not establish that the same requirements "
                "apply to all scheduled commercial banks. "
            ) * 5
        }
    ]

    proposed_response = (
        "The Small Finance Bank-specific directions apply "
        "to Karnataka Bank."
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
    print("Summary:", result["validation_summary"])
    print("Response:", result["validated_response"])
    print("Issues:", result["issues"])


if __name__ == "__main__":
    asyncio.run(run_test())

