
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
        "What are the latest RBI guidelines applicable "
        "to Karnataka Bank?"
    )

    web_findings = [
        {
            "source_title": "RBI Regulatory Direction 2026",
            "source_url": "https://www.rbi.org.in/example",
            "retrieval_status": "success",
            "source_content": """
            RBI published this regulatory direction on
            15 December 2026.

            The direction becomes effective from
            1 April 2027.

            Regulated entities must comply from the
            specified effective date.
            """
        }
    ]

    proposed_response = (
        "The new RBI direction is currently effective "
        "and Karnataka Bank must comply immediately."
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
