
import os
import json
from datetime import date
from dotenv import load_dotenv

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient


load_dotenv()


async def generate_response(
    question,
    organisation,
    rag_passages=None,
    web_findings=None,
    conversation_history=None
):
    """
    Generate a customer support response using RAG and web evidence.

    The agent must use only the supplied evidence.
    """

    api_key = os.getenv("OPENAI_API_KEY")
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing in .env")

    rag_passages = rag_passages or []
    web_findings = web_findings or []

    model_client = OpenAIChatCompletionClient(
        model=model_name,
        api_key=api_key
    )

    system_message = """
You are a Customer Support Response Generation Agent.

Your responsibility is to prepare an accurate, helpful and
professional response to the customer's question.

You receive:
1. The customer's question.
2. Organisation information.
3. Passages retrieved from the local RAG database.
4. Findings obtained from external web research.

EVIDENCE RULES:

1. Use the supplied RAG passages as evidence for internal
   organisational policies and procedures.

2. Use web findings for current information and external
   verification when they are provided.

3. Do not invent facts, figures, dates, policies or procedures.

4. Do not use general knowledge to fill gaps in the evidence.

5. Do not mix information belonging to different organisations.

6. Do not claim that information is current unless the supplied
   evidence supports that conclusion.

7. Treat web search snippets as preliminary evidence.
   If the supplied web material is insufficient to verify a claim,
   clearly qualify the answer.

8. If evidence is insufficient, explain what could not be verified.
   Do not guess.

9. For external web findings, use source_content from successfully
   retrieved sources as the primary evidence.

10. Do not treat search snippets, titles or search-result descriptions
    as sufficient proof for detailed regulatory claims.

11. Do not use information from a source whose retrieval_status
    is not "success".

12. Never assume that an external regulatory requirement is explicitly
    included in the organisation's internal SOP.

13. Do not introduce standard banking practices, appeal rights,
    eligibility conditions, exemptions or procedures unless they
    are explicitly supported by the supplied evidence.

14. Preserve the exact applicability conditions, effective dates,
    exceptions and institutional categories stated in the sources.

15. If a claim cannot be verified from the supplied evidence,
    omit the claim and mention the limitation where relevant.

WRITING STYLE:

- Be professional and customer-friendly.
- Answer the question directly.
- If the customer asks to reach a higher official, escalate a complaint, or
  close an account, provide the supported procedure or next step and gently
  ask the reason (for example, unresolved service issue, failed transaction,
  access problem, charges, or another concern). Do not make the reason a
  prerequisite for giving the available answer.
- Use short paragraphs and bullet points where helpful.
- Explain technical terms when necessary.
- Preserve important conditions and exceptions.
- Avoid unnecessary technical explanations about RAG or AI agents.

SOURCE REFERENCES:

For RAG evidence, use the supplied filename and page number.

For web evidence, use the supplied source title and URL.

Never invent a source reference.

OUTPUT:

Return valid JSON only, using this structure:

{
    "answer": "Customer-facing response",
    "answer_status": "answered | partially_answered | insufficient_evidence",
    "key_points": [],
    "sources": [
        {
            "source_type": "rag | web",
            "source_name": "Document or webpage title",
            "page": "Page number or null",
            "url": "URL or null"
        }
    ],
    "limitations": []
}

Do not include Markdown code fences.
Return JSON only.
"""

    agent = AssistantAgent(
        name="response_generation_agent",
        model_client=model_client,
        system_message=system_message
    )

    current_date = date.today().isoformat()

    task = f"""
    CURRENT DATE:
    {current_date}

IMPORTANT DATE INTERPRETATION:
- Treat the current date above as the reference date.
- If a policy or regulation became effective before the current date,
  describe it as already effective.
- If its effective date is after the current date,
  describe it as upcoming or not yet effective.
- Do not describe an already effective regulation as future.
- Preserve transition periods and applicability conditions stated in the evidence.

CUSTOMER QUESTION:
{question}

PREVIOUS CONVERSATION CONTEXT:
{conversation_history or "No previous messages; treat this as a new conversation."}

ORGANISATION:
{json.dumps(organisation, ensure_ascii=False, default=str)}

RAG EVIDENCE:
{json.dumps(rag_passages, ensure_ascii=False, default=str)}

WEB RESEARCH FINDINGS:
{json.dumps(web_findings, ensure_ascii=False, default=str)}

Prepare the customer-facing answer using only the supplied evidence.

Return the required JSON response.
"""

    try:

        result = await agent.run(task=task)

        final_content = ""

        for message in reversed(result.messages):

            content = getattr(message, "content", None)

            if isinstance(content, str) and content.strip():
                final_content = content
                break

        if not final_content:
            raise RuntimeError(
                "Response Generation Agent returned no response."
            )

        try:
            parsed_result = json.loads(final_content)

        except json.JSONDecodeError as error:

            raise ValueError(
                f"Agent returned invalid JSON: {final_content}"
            ) from error

        allowed_statuses = {
            "answered",
            "partially_answered",
            "insufficient_evidence"
        }

        if parsed_result.get("answer_status") not in allowed_statuses:
            raise ValueError("Invalid answer_status returned by agent.")

        if not isinstance(parsed_result.get("answer"), str):
            raise ValueError("Agent did not return a valid answer.")

        return parsed_result

    finally:
        await model_client.close()
