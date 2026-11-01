
import os
import json

from dotenv import load_dotenv

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient


load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


SYSTEM_MESSAGE = """
You are a Document Intelligence Specialist.

Your responsibility is to analyse customer-support documents
and identify the organisation, industry and document scope.

Carefully inspect the supplied document content.

Identify:

1. Organisation name.
2. Industry or business sector.
3. Official website, only if supported by the document.
4. Document category.
5. Main products and services.
6. Important topics.
7. Relevant terminology.
8. Organisation-specific research restrictions.
9. Any uncertainty or missing information.

IMPORTANT RULES:

- Do not guess the organisation.
- Do not infer an official website without sufficient evidence.
- Do not assume the document belongs to a particular organisation
  merely because it mentions that organisation.
- Distinguish the document owner from organisations mentioned
  incidentally.
- If the organisation cannot be identified, state UNKNOWN.
- Identify multiple organisations if the document genuinely
  covers more than one organisation.
- Use the actual document content as your evidence.

Return ONLY valid JSON using this structure:

{
    "organisation_name": "",
    "industry": "",
    "official_website": "",
    "document_category": "",
    "products_services": [],
    "topics": [],
    "terminology": [],
    "research_scope": "",
    "confidence": "high/medium/low",
    "evidence": [],
    "uncertainties": []
}
"""


async def analyse_document(document_text):

    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is missing in .env")

    model_client = OpenAIChatCompletionClient(
        model=OPENAI_MODEL,
        api_key=OPENAI_API_KEY
    )

    agent = AssistantAgent(
        name="Document_Intelligence_Agent",
        model_client=model_client,
        system_message=SYSTEM_MESSAGE
    )

    try:
        result = await agent.run(
            task=(
                "Analyse the following uploaded document and identify "
                "its organisation and research scope.\n\n"
                "DOCUMENT CONTENT:\n"
                + document_text
            )
        )

        response = result.messages[-1].content

        if not isinstance(response, str):
            raise ValueError("Agent returned an unexpected response.")

        # Extract JSON safely.
        start = response.find("{")
        end = response.rfind("}")

        if start == -1 or end == -1:
            raise ValueError("Agent did not return valid JSON.")

        extracted_json = response[start:end + 1]

        data = json.loads(extracted_json)

        required_fields = [
            "organisation_name",
            "industry",
            "official_website",
            "document_category",
            "products_services",
            "topics",
            "terminology",
            "research_scope",
            "confidence",
            "evidence",
            "uncertainties"
        ]

        missing = [
            field for field in required_fields
            if field not in data
        ]

        if missing:
            raise ValueError(
                f"Missing JSON fields: {missing}"
            )

        return data

    finally:
        await model_client.close()
