
import json
from typing import Any

from database.db_manager import (
    init_db,
    get_connection,
    create_conversation,
    conversation_belongs_to_customer,
    update_conversation,
    save_message,
    get_conversation_messages,
    log_agent_activity
    ,update_message_metadata
)
from database.admin_analytics import classify_query, classify_customer_signals

from rag.retrieval import search_knowledge_base

from agents.query_understanding_agent import understand_query
from agents.web_research_agent import run_web_research_agent
from agents.response_generation_agent import generate_response
from agents.response_validation_agent import validate_response


def load_organisation_context(organisation_id, document_id=None):
    """
    Load organisation and document metadata from SQLite.
    """

    with get_connection() as conn:

        if document_id is not None:

            row = conn.execute("""
                SELECT
                    o.id AS organisation_id,
                    o.name AS organisation_name,
                    o.domain,
                    o.official_website,
                    o.metadata_json AS organisation_metadata,
                    d.id AS document_id,
                    d.filename,
                    d.metadata_json AS document_metadata
                FROM organisations o
                JOIN documents d
                    ON d.organisation_id = o.id
                WHERE o.id = ? AND d.id = ?
            """, (organisation_id, document_id)).fetchone()

        else:

            row = conn.execute("""
                SELECT
                    o.id AS organisation_id,
                    o.name AS organisation_name,
                    o.domain,
                    o.official_website,
                    o.metadata_json AS organisation_metadata,
                    d.id AS document_id,
                    d.filename,
                    d.metadata_json AS document_metadata
                FROM organisations o
                JOIN documents d
                    ON d.organisation_id = o.id
                WHERE o.id = ?
                ORDER BY d.uploaded_at DESC
                LIMIT 1
            """, (organisation_id,)).fetchone()

    if not row:
        raise ValueError(
            "Organisation or registered document not found."
        )

    organisation_metadata = json.loads(
        row["organisation_metadata"] or "{}"
    )

    document_metadata = json.loads(
        row["document_metadata"] or "{}"
    )

    organisation = {
        **organisation_metadata,

        # Authoritative organisation fields from SQLite
        "id": row["organisation_id"],
        "name": row["organisation_name"],
        "industry": row["domain"],
        "official_website": row["official_website"]
    }

    # Use document metadata first, then organisation metadata.
    document_context = {
        "document_id": row["document_id"],
        "filename": row["filename"],
        **organisation_metadata,
        **document_metadata
    }

    # The organisation record is authoritative for these fields.
    document_context["official_website"] = (
        row["official_website"]
    )

    return organisation, document_context


def save_activity(
    conversation_id,
    agent_name,
    activity_type,
    description,
    input_data=None,
    output_data=None,
    status="completed"
):
    """
    Save an agent activity in SQLite.
    """

    return log_agent_activity(
        conversation_id=conversation_id,
        agent_name=agent_name,
        activity_type=activity_type,
        description=description,
        input_data=input_data,
        output_data=output_data,
        status=status
    )


async def run_customer_support(
    question,
    organisation_id,
    conversation_id=None,
    document_id=None,
    customer_id=None,
    progress_callback=None
) -> dict[str, Any]:
    """
    Main multi-agent orchestration function.

    Runs the agents conditionally and stores the interaction
    in SQLite.
    """

    if not question or not question.strip():
        raise ValueError("Customer question cannot be empty.")

    init_db()

    question = question.strip()

    def report(stage, description):
        if progress_callback:
            progress_callback(stage, description)

    # --------------------------------------------------
    # 1. LOAD ORGANISATION AND DOCUMENT CONTEXT
    # --------------------------------------------------

    organisation, document_metadata = load_organisation_context(
        organisation_id=organisation_id,
        document_id=document_id
    )

    # Create a new conversation if one was not supplied.
    if conversation_id is None:

        conversation_id = create_conversation(
            title=question[:80],
            organisation_id=organisation_id,
            customer_id=customer_id
        )

    else:
        # Verify that the supplied conversation exists
        # and belongs to the requested organisation.
        with get_connection() as conn:

            row = conn.execute("""
                SELECT id, organisation_id
                FROM conversations
                WHERE id = ?
            """, (conversation_id,)).fetchone()

        if not row:
            raise ValueError("Conversation not found.")

        if row["organisation_id"] != organisation_id:
            raise ValueError(
                "Conversation does not belong to this organisation."
            )
        if customer_id is not None and not conversation_belongs_to_customer(conversation_id, customer_id):
            raise ValueError("Conversation does not belong to this customer.")

    previous_messages = get_conversation_messages(conversation_id)
    conversation_history = "\n".join(
        f"{message['role'].capitalize()}: {message['content']}"
        for message in previous_messages[-10:]
    )

    # Save the customer's message.
    user_message_id = save_message(
        conversation_id=conversation_id,
        role="user",
        content=question
    )

    print("\n" + "=" * 65)
    print("CUSTOMER SUPPORT ORCHESTRATOR")
    print("=" * 65)

    print("Conversation ID:", conversation_id)
    print("Organisation:", organisation["name"])
    print("Question:", question)

    # --------------------------------------------------
    # 2. QUERY UNDERSTANDING
    # --------------------------------------------------

    report(1, "Understanding your question")

    print("\n[1/6] Running Query Understanding Agent...")

    routing = await understand_query(
        question=question,
        conversation_history=conversation_history,
        organisation_context={
            **organisation,
            "topics": document_metadata.get("topics", []),
            "document_category": document_metadata.get(
                "document_category"
            ),
            "research_scope": document_metadata.get(
                "research_scope"
            )
        }
    )

    save_activity(
        conversation_id=conversation_id,
        agent_name="query_understanding_agent",
        activity_type="query_analysis",
        description="Analysed customer question and prepared routing plan.",
        input_data={"question": question},
        output_data=routing
    )
    service, query_type, issue = classify_query(question, routing)
    signals = classify_customer_signals(question)
    update_message_metadata(user_message_id, {
        "service": service, "query_type": query_type, "issue": issue,
        **signals,
        "routing_intent": routing.get("intent"), "routing_topic": routing.get("topic")
    })

    print("Intent:", routing.get("intent"))
    print("Topic:", routing.get("topic"))
    print("RAG required:", routing.get("requires_rag"))
    print("Web research required:", routing.get("requires_web_research"))

    # --------------------------------------------------
    # 3. RAG RETRIEVAL
    # --------------------------------------------------

    report(2, "Searching organisation support documents")

    rag_passages = []

    if routing.get("requires_rag"):

        print("\n[2/6] Retrieving information from ChromaDB...")

        rag_question = (
            routing.get("rag_search_query") or question
        )

        rag_passages = search_knowledge_base(
            question=rag_question,
            organisation_id=organisation_id,
            # Search the organisation's complete persistent knowledge base by
            # default. An explicitly supplied document_id remains restrictive.
            document_id=document_id,
            top_k=5
        )

        save_activity(
            conversation_id=conversation_id,
            agent_name="rag_retrieval",
            activity_type="knowledge_retrieval",
            description="Retrieved relevant passages from ChromaDB.",
            input_data={
                "question": rag_question,
                "organisation_id": organisation_id
            },
            output_data={
                "passage_count": len(rag_passages),
                "passages": rag_passages
            }
        )

        print("Retrieved passages:", len(rag_passages))

    else:

        print("\n[2/6] RAG retrieval skipped.")

        save_activity(
            conversation_id=conversation_id,
            agent_name="rag_retrieval",
            activity_type="knowledge_retrieval",
            description="RAG retrieval was not required.",
            output_data={"passage_count": 0}
        )

    # --------------------------------------------------
    # 4. WEB RESEARCH
    # --------------------------------------------------

    report(3, "Checking current official information" if routing.get("requires_web_research") else "Web research not required")

    web_result = {
        "research_required": False,
        "research_findings": [],
        "summary": "Web research was not required."
    }

    if routing.get("requires_web_research"):

        print("\n[3/6] Running AutoGen Web Research Agent...")

        research_question = (
            routing.get("web_research_question") or question
        )

        research_scope = routing.get(
            "research_scope",
            "organisation"
        )

        web_result = await run_web_research_agent(
            question=research_question,
            organisation=organisation,
            document_metadata=document_metadata,
            rag_passages=rag_passages,
            conversation_id=conversation_id,
            research_scope=research_scope,
            must_research=routing.get("requires_web_research", False))

        # Save research activity.
        save_activity(
            conversation_id=conversation_id,
            agent_name="web_research_agent",
            activity_type="web_research",
            description="Performed organisation-specific web research.",
            input_data={
                "question": research_question,
                "research_scope": research_scope
            },
            output_data=web_result
        )

        print(
            "Research findings:",
            len(web_result.get("research_findings", []))
        )

    else:

        print("\n[3/6] Web research skipped.")

        save_activity(
            conversation_id=conversation_id,
            agent_name="web_research_agent",
            activity_type="web_research",
            description="Web research was not required.",
            output_data=web_result
        )

    web_findings = web_result.get("research_findings", [])

    # --------------------------------------------------
    # 5. RESPONSE GENERATION
    # --------------------------------------------------

    report(4, "Preparing a customer support response")

    print("\n[4/6] Generating customer response...")

    generation_result = await generate_response(
        question=question,
        organisation=organisation,
        rag_passages=rag_passages,
        web_findings=web_findings,
        conversation_history=conversation_history
    )

    save_activity(
        conversation_id=conversation_id,
        agent_name="response_generation_agent",
        activity_type="response_generation",
        description="Generated customer-facing response.",
        input_data={
            "question": question,
            "rag_passage_count": len(rag_passages),
            "web_finding_count": len(web_findings)
        },
        output_data=generation_result
    )

    proposed_response = generation_result.get("answer", "")

    print(
        "Generation status:",
        generation_result.get("answer_status")
    )

    # --------------------------------------------------
    # 6. RESPONSE VALIDATION
    # --------------------------------------------------

    report(5, "Validating the response against available evidence")

    print("\n[5/6] Validating generated response...")

    validation_result = await validate_response(
        question=question,
        organisation=organisation,
        proposed_response=proposed_response,
        rag_passages=rag_passages,
        web_findings=web_findings,
        conversation_history=conversation_history
    )

    save_activity(
        conversation_id=conversation_id,
        agent_name="response_validation_agent",
        activity_type="response_validation",
        description="Validated the generated customer response.",
        input_data={
            "proposed_response": proposed_response
        },
        output_data=validation_result
    )

    validation_status = validation_result.get(
        "validation_status"
    )

    print("Validation status:", validation_status)

    # --------------------------------------------------
    # 7. SELECT FINAL RESPONSE
    # --------------------------------------------------

    if validation_status == "approved":

        final_answer = (
            validation_result.get("validated_response")
            or proposed_response
        )

        final_status = "approved"

    elif validation_status == "needs_revision":

        corrected_response = validation_result.get(
            "validated_response", ""
        )

        if corrected_response:

            print("\nRevalidating corrected response...")

            second_validation = await validate_response(
                question=question,
                organisation=organisation,
                proposed_response=corrected_response,
                rag_passages=rag_passages,
                web_findings=web_findings,
                conversation_history=conversation_history
            )

            save_activity(
                conversation_id=conversation_id,
                agent_name="response_validation_agent",
                activity_type="response_revalidation",
                description="Revalidated the corrected response.",
                input_data={
                    "corrected_response": corrected_response
                },
                output_data=second_validation
            )

            if second_validation.get("validation_status") == "approved":

                final_answer = (
                    second_validation.get("validated_response")
                    or corrected_response
                )

                final_status = "approved_after_revision"

            else:

                final_answer = (
                    "I could not verify all the details needed "
                    "to provide a reliable answer. Please contact "
                    "the organisation for confirmation."
                )

                final_status = "insufficient_evidence"

        else:

            final_answer = (
                "I could not verify the information required "
                "to provide a reliable answer."
            )

            final_status = "insufficient_evidence"

    else:

        final_answer = (
            validation_result.get("validated_response")
            or "I could not verify the information required "
               "to provide a reliable answer. Please contact "
               "the organisation for confirmation."
        )

        final_status = "insufficient_evidence"

    report(6, "Response ready")

    # --------------------------------------------------
    # 8. SAVE COMPLETE INTERACTION
    # --------------------------------------------------

    print("\n[6/6] Saving interaction in SQLite...")

    response_metadata = {
        "answer_status": final_status,
        "validation_status": validation_status,
        "organisation_id": organisation_id,
        "document_id": document_metadata["document_id"],
        "routing": routing,
        "generation": generation_result,
        "validation": validation_result,
        "research": web_result
    }

    assistant_message_id = save_message(
        conversation_id=conversation_id,
        role="assistant",
        agent_name="customer_support_orchestrator",
        content=final_answer,
        metadata=response_metadata
    )

    update_conversation(
        conversation_id=conversation_id,
        status="active",
        customer_id=customer_id
    )

    print("\nCUSTOMER SUPPORT PROCESS COMPLETED")
    print("=" * 65)

    print("Conversation ID:", conversation_id)
    print("Final status:", final_status)

    return {
        "conversation_id": conversation_id,
        "user_message_id": user_message_id,
        "assistant_message_id": assistant_message_id,
        "organisation": organisation,
        "question": question,
        "answer": final_answer,
        "answer_status": final_status,
        "routing": routing,
        "rag_passages": rag_passages,
        "web_research": web_result,
        "generation": generation_result,
        "validation": validation_result
    }
