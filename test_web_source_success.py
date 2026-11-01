
import asyncio
import json

import agents.web_research_agent as web_agent


# -------------------------------------------------
# MOCK SEARCH RESULT
# -------------------------------------------------

def mock_search_web(**kwargs):

    print("\nUsing temporary W3C test search result...")

    return {
        "status": "success",
        "search_query": "W3C dummy PDF test",
        "results": {
            "organic_results": [
                {
                    "title": "W3C Dummy PDF File",
                    "url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
                    "snippet": "A public dummy PDF file provided by W3C.",
                    "position": 1
                }
            ]
        }
    }


# Replace the real search function temporarily.
web_agent.search_web = mock_search_web


# -------------------------------------------------
# RUN WEB RESEARCH AGENT
# -------------------------------------------------

async def main():

    organisation = {
        "id": 999,
        "name": "W3C Test Organisation",
        "official_website": "https://www.w3.org"
    }

    document_metadata = {
        "official_website": "https://www.w3.org",
        "topics": ["PDF retrieval testing"]
    }

    question = "What information is available in the W3C dummy PDF?"

    print("\nStarting Web Research Agent...")
    print("=" * 60)

    result = await web_agent.run_web_research_agent(
        question=question,
        organisation=organisation,
        document_metadata=document_metadata,
        rag_passages=[],
        research_scope="organisation",
        must_research=True
    )

    print("\nFULL AGENT RESPONSE")
    print("=" * 60)

    print(json.dumps(
        result,
        indent=4,
        ensure_ascii=False,
        default=str
    ))

    print("\nSOURCE RETRIEVAL STATUS")
    print("=" * 60)

    for source in result.get("retrieved_sources", []):

        print("Title:", source["source_title"])
        print("URL:", source["source_url"])
        print("Status:", source["retrieval_status"])
        print("Content type:", source["content_type"])
        print("-" * 60)

    print("\nTEST COMPLETED")


if __name__ == "__main__":
    asyncio.run(main())

