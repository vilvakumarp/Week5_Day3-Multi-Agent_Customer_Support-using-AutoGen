
import os
import json
import asyncio


from dotenv import load_dotenv

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient
from tools.web_search import search_web
from urllib.parse import urlparse
from tools.source_retriever import retrieve_source, is_allowed_domain


load_dotenv()


def get_allowed_domains(official_website, research_scope):
    """
    Build the permitted source-domain list for this organisation.
    """

    allowed_domains = []

    if official_website:
        website = official_website.strip()

        if not website.startswith(("https://", "http://")):
            website = "https://" + website

        hostname = urlparse(website).hostname

        if hostname:
            allowed_domains.append(hostname.lower())

    if research_scope == "regulatory":
        allowed_domains.append("rbi.org.in")

    return list(set(allowed_domains))



def create_web_research_tool(
    organisation_id,
    organisation_name,
    topics=None,
    official_website=None,
    conversation_id=None,
    research_scope="organisation",
    retrieved_sources=None
):
    """
    Creates an organisation-restricted research tool.

    Searches the web, retrieves permitted original sources,
    and retains extracted content for downstream agents.
    """

    if retrieved_sources is None:
        retrieved_sources = []

    allowed_domains = get_allowed_domains(
        official_website,
        research_scope
    )

    def search_organisation_web(question: str) -> str:

        result = search_web(
            organisation_id=organisation_id,
            organisation_name=organisation_name,
            question=question,
            topics=topics,
            official_website=official_website,
            research_scope=research_scope,
            conversation_id=conversation_id,
            cache_hours=24
        )

        search_data = result.get("results", {})

        search_results = search_data.get(
            "organic_results", []
        )
        if not isinstance(search_results, list):
            search_results = []

        print("\nNumber of organic search results:", len(search_results))

        # Retrieve only a limited number of permitted sources.
        # Retrieve up to five unique sources from approved domains.
        retrieved_count = 0
        max_sources = 5

        for item in search_results:

            if retrieved_count >= max_sources:
                break

            source_url = item.get("url")

            if not source_url:
                continue

            # Avoid retrieving the same URL more than once.
            if any(
                source.get("source_url") == source_url
                for source in retrieved_sources
            ):
                continue

            # Check whether the domain is approved.
            hostname = urlparse(source_url).hostname

            if not hostname or not is_allowed_domain(
                hostname,
                allowed_domains
            ):
                continue

            source = retrieve_source(
                source_url,
                allowed_domains=allowed_domains,
                timeout=30,
                max_bytes=20_000_000
            )

            source_record = {
                "source_title": item.get("title", ""),
                "source_url": source_url,
                "source_snippet": item.get("snippet", ""),
                "retrieval_status": source["status"],
                "retrieval_error": source.get("error"),
                "source_content": source.get("full_text", ""),
                "content_type": source.get("content_type"),
                "final_url": source.get("final_url"),
                "source_pages": source.get("pages", [])
            }

            retrieved_sources.append(source_record)

            # Attach retrieval information to the search result.
            item["retrieval_status"] = source["status"]
            item["retrieval_error"] = source.get("error")

            if source["status"] == "success":
                item["source_content"] = source["full_text"][:12000]
                item["content_type"] = source["content_type"]
                item["final_url"] = source["final_url"]

            retrieved_count += 1


        result["retrieved_source_count"] = len(retrieved_sources)
        result["allowed_domains"] = allowed_domains

        return json.dumps(
            result,
            ensure_ascii=False,
            default=str
        )

    return search_organisation_web



async def run_web_research_agent(
    question,
    organisation,
    document_metadata,
    rag_passages,
    conversation_id=None,
    research_scope="organisation",
    must_research=False
):
    """
    Runs the AutoGen Web Research Agent.

    The agent evaluates RAG evidence and searches the web
    only when additional information or current verification
    is required.
    """

    api_key = os.getenv("OPENAI_API_KEY")
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing in .env")

    organisation_id = organisation["id"]
    organisation_name = organisation["name"]

    topics = document_metadata.get("topics", [])
    official_website = (
        document_metadata.get("official_website")
        or organisation.get("official_website")
    )

    # Store original retrieved source content separately.
    retrieved_sources = []

    # Prepare the organisation-restricted search tool.
    search_tool = create_web_research_tool(
        organisation_id=organisation_id,
        organisation_name=organisation_name,
        topics=topics,
        official_website=official_website,
        conversation_id=conversation_id,
        research_scope=research_scope,
        retrieved_sources=retrieved_sources)

    
    # -------------------------------------------------
    # DETERMINISTIC WEB SEARCH
    # -------------------------------------------------

    prefetched_search_result = None

    if must_research:

        print("\nMandatory research enabled.")
        print("Executing web search directly from Python...")

        raw_search_result = search_tool(question)

        try:
            prefetched_search_result = json.loads(raw_search_result)

        except json.JSONDecodeError:
            prefetched_search_result = {
                "status": "error",
                "error": "Search tool returned invalid JSON."
            }

        print(
            "Sources retrieved:",
            len(retrieved_sources)
        )


    # Create the AutoGen model client.
    model_client = OpenAIChatCompletionClient(
        model=model_name,
        api_key=api_key
    )

    system_message = """
You are an Organisation-Specific Web Research Agent
working in a customer support system.

YOUR RESPONSIBILITIES:

1. Analyse the customer's question.
2. Examine the organisation profile and uploaded document topics.
3. Review the information retrieved from the local RAG database.
4. Decide whether additional web research is necessary.

WHEN TO SEARCH:

Search the web when:
- The RAG passages do not sufficiently answer the question.
- Important details are missing.
- The customer asks for current or latest information.
- A policy, regulation, contact detail or procedure needs verification.

DO NOT SEARCH when:
- The RAG passages already provide a sufficient answer.
- The question is unrelated to external information.
- The customer is only asking for an explanation of supplied content.

ORGANISATION RESTRICTIONS:

- Always keep the identified organisation as the primary context.
- Never substitute another bank or organisation.
- For regulatory questions, you may research relevant regulators
  such as RBI, while retaining the organisation context.
- Do not invent official websites or source URLs.
- Use the supplied search tool for all web searches.

SOURCE HANDLING:

- Prefer official organisation websites and regulator websites.
- Use the supplied search tool for all web searches.
- Examine extracted source_content when available.
- Distinguish actual extracted content from search snippets.
- Do not make factual claims based only on a source title.
- Do not invent policy details, dates or numerical values.
- If retrieval_status is error, do not treat the source as verified.
- If only snippets are available, clearly identify the limitation.
- Preserve source titles and original URLs.

OUTPUT:

Return a structured JSON response with these fields:

{
    "research_required": true,
    "reason": "Reason for searching or not searching",
    "organisation": "Organisation name",
    "research_findings": [
        {
            "finding": "Research finding",
            "source_title": "Source title",
            "source_url": "Source URL",
            "source_snippet": "Available supporting snippet"
        }
    ],
    "rag_gaps": [],
    "limitations": [],
    "summary": "Short summary of the research"
}

If no web search is required, return an empty research_findings list.

Do not fabricate findings, citations or URLs.
Return valid JSON only.
"""

    # If mandatory research has already been executed by Python,
    # do not give AutoGen the search tool again.

    agent_tools = [] if must_research else [search_tool]

    agent = AssistantAgent(
        name="web_research_agent",
        model_client=model_client,
        tools=list(agent_tools),
        system_message=system_message,
        reflect_on_tool_use=True)

    # Prepare the complete research task.
    
    task = f"""
    CUSTOMER QUESTION:
    {question}

    ORGANISATION PROFILE:
    {json.dumps(organisation, ensure_ascii=False, default=str)}

    RESEARCH SCOPE:
    {research_scope}

    MANDATORY RESEARCH INSTRUCTION:
    {must_research}

    UPLOADED DOCUMENT METADATA:
    {json.dumps(document_metadata, ensure_ascii=False, default=str)}

    INFORMATION RETRIEVED FROM LOCAL RAG:
    {json.dumps(rag_passages, ensure_ascii=False, default=str)}

    WEB SEARCH RESULTS ALREADY RETRIEVED BY PYTHON:

    {json.dumps(prefetched_search_result, ensure_ascii=False, default=str)}

    ACTUAL SOURCE CONTENT:

    {json.dumps(retrieved_sources, ensure_ascii=False, default=str)}

    RESEARCH DECISION:

    If MANDATORY RESEARCH INSTRUCTION is True:

    - Web search has already been executed by Python.
    - Examine the supplied WEB SEARCH RESULTS.
    - Examine ACTUAL SOURCE CONTENT.
    - Do not invent additional search results or URLs.
    - Do not create findings that are unsupported by the retrieved evidence.
    - If a source could not be retrieved, identify that limitation.
    - If no source content was retrieved, clearly report insufficient evidence.
    - Do not treat search snippets as verified policy content.

    If MANDATORY RESEARCH INSTRUCTION is False:

    - Evaluate whether the RAG passages are sufficient.
    - Search only when additional information or verification is needed.

    After searching:

    - Examine the returned search results.
    - Extract relevant findings and source URLs.
    - Prefer official organisation and regulator sources.
    - Distinguish current information from older documents.
    - Do not treat search snippets as fully verified policy text.

    Return the final structured JSON response.
    """


    try:
        result = await agent.run(task=task)

                # Extract the final response from the assistant.
        # Ignore tool execution messages and tool outputs.

        assistant_messages = [
            message
            for message in result.messages
            if isinstance(message, TextMessage)
            and message.source == "web_research_agent"
        ]

        if not assistant_messages:
            message_details = [
                {
                    "type": type(message).__name__,
                    "source": getattr(message, "source", None)
                }
                for message in result.messages
            ]

            raise RuntimeError(
                "No final TextMessage received from Web Research Agent. "
                f"Messages: {message_details}"
            )

        final_content = assistant_messages[-1].content

        if not isinstance(final_content, str) or not final_content.strip():
            raise RuntimeError(
                "The Web Research Agent returned an empty response."
            )

        # Parse the final assistant response as JSON.
        
        # Remove Markdown JSON code fences if present.
        cleaned_content = final_content.strip()

        if cleaned_content.startswith("```"):
            lines = cleaned_content.splitlines()

            if lines[-1].strip() == "```":
                lines = lines[:-1]

            lines = lines[1:]
            cleaned_content = "\n".join(lines).strip()

        try:
            parsed_result = json.loads(cleaned_content)

        except json.JSONDecodeError as e:
            parsed_result = {
                "research_required": None,
                "organisation": organisation_name,
                "raw_response": final_content,
                "research_findings": [],
                "parse_error": str(e)
            }



        # Attach actual retrieved source content to the findings.
        findings = parsed_result.get("research_findings", [])

        for source in retrieved_sources:

            matching_finding = next(
                (
                    finding for finding in findings
                    if finding.get("source_url") == source["source_url"]
                ),
                None
            )

            if matching_finding:
                matching_finding.update({
                    "source_content": source["source_content"],
                    "content_type": source["content_type"],
                    "retrieval_status": source["retrieval_status"],
                    "retrieval_error": source["retrieval_error"],
                    "source_pages": source["source_pages"]
                })

            elif source["retrieval_status"] == "success":

                findings.append({
                    "finding": source["source_snippet"],
                    "source_title": source["source_title"],
                    "source_url": source["source_url"],
                    "source_snippet": source["source_snippet"],
                    "source_content": source["source_content"],
                    "content_type": source["content_type"],
                    "retrieval_status": "success",
                    "source_pages": source["source_pages"]
                })

                # Keep only findings supported by successfully retrieved source content.
        verified_findings = []

        for finding in findings:

            if (
                finding.get("retrieval_status") == "success"
                and finding.get("source_content", "").strip()
                and finding.get("source_url")
            ):
                verified_findings.append(finding)

        parsed_result["research_findings"] = verified_findings

        # If no source content was retrieved, report insufficient evidence.
        if not verified_findings:
            parsed_result["evidence_status"] = "insufficient_evidence"

            parsed_result["summary"] = (
                "Insufficient verified evidence is available. "
                "The search results were found, but the original source "
                "content could not be retrieved."
            )

        # Keep retrieval diagnostics available for debugging.
        parsed_result["retrieved_sources"] = [
            {
                "source_title": source["source_title"],
                "source_url": source["source_url"],
                "retrieval_status": source["retrieval_status"],
                "retrieval_error": source["retrieval_error"],
                "content_type": source["content_type"]
            }
            for source in retrieved_sources
        ]

        return parsed_result


    finally:
        await model_client.close()
