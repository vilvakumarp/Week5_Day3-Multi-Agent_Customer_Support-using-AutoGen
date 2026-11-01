
import os
import json

from dotenv import load_dotenv

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient


load_dotenv()


async def understand_query(question, organisation_context, conversation_history=None):

    """
    Analyse a customer question and return structured intent,
    topic, organisation and retrieval requirements.
    """

    api_key = os.getenv("OPENAI_API_KEY")
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing in .env")

    model_client = OpenAIChatCompletionClient(
        model=model_name,
        api_key=api_key
    )

    system_message = """
You are a Query Understanding Agent in a multi-agent
customer support system.

Your responsibility is to understand the customer's question
and prepare a structured plan for other agents.

You do NOT answer the customer's question.

You must analyse:

1. Customer intent.
2. Relevant organisation.
3. Relevant document topics.
4. Whether local RAG retrieval is required.
5. Whether external web research is required.
6. Whether current information is required.
7. Whether the query involves regulatory information.
8. The best search question for the RAG agent.
9. Whether the customer is requesting escalation to a higher official or
   account closure, and whether the reason for that request is stated.

IMPORTANT RULES:

- Use the supplied organisation context.
- Do not invent organisation details.
- Do not substitute another organisation.
- Prefer RAG for organisation-specific policies and procedures.
- Recommend web research when current information or external
  verification is necessary.
- Regulatory queries may require both RAG and regulatory research.
- If the question is ambiguous, identify the ambiguity.
- For escalation or account-closure requests, capture any stated reason and
  identify when a brief follow-up question would help understand the issue.
- Do not answer the customer's question.

Return valid JSON only, using this structure:

{
    "organisation": "Organisation name",
    "intent": "Short intent identifier",
    "topic": "Relevant topic",
    "query_type": "organisation_specific | regulatory | general",
    "requires_rag": true,
    "requires_web_research": false,
    "requires_current_information": false,
    "research_scope": "organisation | regulatory",
    "rag_search_query": "Optimised question for document retrieval",
    "web_research_question": "Specific question for web research",
    "ambiguities": [],
    "reasoning": "Short explanation for the routing decision"
}


ADDITIONAL ROUTING RULES:

1. ORGANISATION-SPECIFIC QUESTIONS

If the customer asks about a named organisation's:
- Products
- Services
- Interest rates
- Charges
- Policies
- Procedures
- Customer support

Set query_type to "organisation_specific".

Do not classify an organisation-specific product or service
question as "general".

2. RAG TOPIC MATCHING

Compare the customer question with the supplied organisation
document topics.

If the question overlaps with an available document topic,
set requires_rag to true.

3. COMBINED RESEARCH

RAG and web research are not mutually exclusive.

For example:
- Latest RBI guidelines about customer complaints:
  requires_rag = true
  requires_web_research = true
  research_scope = "regulatory"

- Current Karnataka Bank savings interest rate:
  requires_rag = false if no relevant document topic exists
  requires_web_research = true
  research_scope = "organisation"

4. CURRENT INFORMATION

If the customer explicitly asks for latest, current, today's,
or updated information, set requires_current_information = true.

Do not assume that an old uploaded document contains
the latest information.


Use boolean values for the true/false fields.
Do not include Markdown code fences.
"""

    agent = AssistantAgent(
        name="query_understanding_agent",
        model_client=model_client,
        system_message=system_message
    )

    task = f"""
ORGANISATION CONTEXT:
{json.dumps(organisation_context, ensure_ascii=False, default=str)}

CUSTOMER QUESTION:
{question}

PREVIOUS CONVERSATION CONTEXT:
{conversation_history or "No previous messages; treat this as a new conversation."}

Analyse this question and return the structured JSON routing plan.
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
            raise RuntimeError("Query Understanding Agent returned no response.")

        try:
            return json.loads(final_content)

        except json.JSONDecodeError as error:

            raise ValueError(
                f"Agent returned invalid JSON: {final_content}"
            ) from error

    finally:
        await model_client.close()
