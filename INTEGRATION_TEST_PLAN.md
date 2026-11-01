# End-to-end integration test plan

## Scope

The test starts with a seeded demo customer, authenticates through the SQLite customer table, submits questions through the existing `run_customer_support()` orchestrator, and verifies customer-owned conversation persistence. It does not change the AutoGen agent architecture, ChromaDB, or uploaded PDFs.

## Scenarios

1. Login: valid account/mobile/PIN succeeds; invalid credentials fail.
2. Internal SOP: query routing requires RAG, retrieves an organisation-owned passage, generates and validates a response, and saves the final answer to the customer conversation.
3. External regulation: query routing requires web research, uses a successfully retrieved official-source finding, generates and validates a response, and saves the final answer.
4. Reopen: the authenticated customer loads the saved conversation and sees the previous user and assistant messages.
5. Isolation: another customer cannot load or update the conversation.

## Execution modes

`test_customer_workflow_integration.py` mocks AutoGen, ChromaDB retrieval, and web search. It verifies orchestration, routing data flow, ownership, and persistence without fabricating live success.

Live validation additionally requires installed project dependencies, a valid `OPENAI_API_KEY`, configured `OPENAI_MODEL`, a working Serper API key, network access, the persisted ChromaDB collection, and the uploaded organisation document. Live results must be reported separately from mocked results.

## Commands

```powershell
python -m pytest -q test_customer_workflow_integration.py
python -m pytest -q
python test_orchestrator_web.py
```

The last two commands are live/dependency-sensitive and must not be represented as passed when collection, API, or network failures occur.
