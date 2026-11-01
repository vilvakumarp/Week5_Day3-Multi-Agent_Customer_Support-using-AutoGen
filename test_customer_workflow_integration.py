import asyncio
from unittest.mock import AsyncMock, patch

from database.db_manager import (
    authenticate_customer,
    conversation_belongs_to_customer,
    create_demo_customer,
    get_connection,
    get_conversation_messages,
    init_db,
    seed_demo_customers,
)
from orchestrator import run_customer_support


def _organisation_id():
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM organisations WHERE name = ? LIMIT 1", ("Karnataka Bank",)).fetchone()
    assert row is not None, "Karnataka Bank organisation must exist for integration testing"
    return row["id"]


def _customer():
    init_db()
    seed_demo_customers()
    customer = authenticate_customer("123456789012", "9876543210", "2468")
    assert customer is not None
    return customer


def _run(question, customer_id, routing, rag, web, answer, progress_callback=None):
    validation = {"validation_status": "approved", "validated_response": answer,
                  "issues": [], "unsupported_claims": [], "supported_claims": [],
                  "evidence_references": [], "corrections_required": False}
    with patch("orchestrator.understand_query", new=AsyncMock(return_value=routing)) as understand, \
         patch("orchestrator.search_knowledge_base", return_value=rag) as search, \
         patch("orchestrator.run_web_research_agent", new=AsyncMock(return_value={
             "research_required": bool(web), "research_findings": web, "summary": "mocked"
         })) as research, \
         patch("orchestrator.generate_response", new=AsyncMock(return_value={
             "answer": answer, "answer_status": "generated"
         })), \
         patch("orchestrator.validate_response", new=AsyncMock(return_value=validation)):
        result = asyncio.run(run_customer_support(
            question=question,
            organisation_id=_organisation_id(),
            customer_id=customer_id,
            progress_callback=progress_callback,
        ))
    return result, understand, search, research


def test_customer_workflow_rag_persistence_and_reopen():
    customer = _customer()
    rag = [{"organisation_id": customer["id"], "content": "Complaints are acknowledged within 2 working days.",
            "filename": "sop.pdf", "page": 2, "document_id": 1}]
    result, understand, search, research = _run(
        "How are complaints acknowledged?", customer["id"],
        {"requires_rag": True, "requires_web_research": False, "rag_search_query": "complaints"},
        rag, [], "Complaints are acknowledged within 2 working days.")
    assert result["answer_status"] == "approved"
    assert result["answer"] == "Complaints are acknowledged within 2 working days."
    assert understand.await_args.kwargs["question"]
    search.assert_called_once()
    research.assert_not_awaited()
    conversation_id = result["conversation_id"]
    assert conversation_belongs_to_customer(conversation_id, customer["id"])
    messages = get_conversation_messages(conversation_id, customer_id=customer["id"])
    assert [message["role"] for message in messages] == ["user", "assistant"]


def test_customer_workflow_web_research_and_isolation():
    customer = _customer()
    web = [{"retrieval_status": "success", "source_title": "RBI source",
            "source_url": "https://rbi.org.in/example",
            "source_content": "The official guidance applies to scheduled banks."}]
    result, _, search, research = _run(
        "What are the latest RBI guidelines?", customer["id"],
        {"requires_rag": False, "requires_web_research": True,
         "web_research_question": "latest RBI guidelines"},
        [], web, "The official guidance applies to scheduled banks.")
    assert result["answer_status"] == "approved"
    search.assert_not_called()
    research.assert_awaited_once()
    conversation_id = result["conversation_id"]
    assert get_conversation_messages(conversation_id, customer_id=customer["id"])
    assert get_conversation_messages(conversation_id, customer_id=customer["id"] + 99999) == []


def test_progress_callback_reports_six_real_stages():
    customer = _customer()
    stages = []
    _run("How are complaints acknowledged?", customer["id"],
         {"requires_rag": True, "requires_web_research": False}, [], [], "Ready",
         lambda stage, description: stages.append((stage, description)))
    assert [stage for stage, _ in stages] == [1, 2, 3, 4, 5, 6]
    assert stages[2][1] == "Web research not required"
    assert stages[-1][1] == "Response ready"
