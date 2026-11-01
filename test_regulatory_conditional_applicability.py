
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
        "Does this RBI direction apply to Karnataka Bank?"
    )

    web_findings = [
        {
            "source_title": "RBI Internal Ombudsman Direction 2026",
            "source_url": "https://www.rbi.org.in/example",
            "retrieval_status": "success",
            "source_content": """
            RBI directions require regulated entities
            having 10 or more banking outlets as of
            31 March 2025 to appoint an Internal Ombudsman.

            Entities that do not meet this threshold
            are not covered by this specific requirement.
            """
        }
    ]

    proposed_response = (
        "Karnataka Bank must appoint an Internal Ombudsman "
        "under this direction."
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
