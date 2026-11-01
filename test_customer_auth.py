from database.db_manager import (
    authenticate_customer,
    conversation_belongs_to_customer,
    create_conversation,
    get_customer_conversations,
    get_connection,
    get_conversation_messages,
    init_db,
    save_message,
    seed_demo_customers,
    update_conversation,
)
from inspect import signature
from orchestrator import run_customer_support


def test_demo_customer_authentication_and_isolation():
    init_db()
    seed_demo_customers()
    customer = authenticate_customer("123456789012", "9876543210", "2468")
    assert customer is not None
    assert customer["account_number_masked"].endswith("9012")
    assert authenticate_customer("123456789012", "9876543210", "0000") is None

    conversation_id = create_conversation("Demo support", organisation_id=None, customer_id=customer["id"])
    assert conversation_belongs_to_customer(conversation_id, customer["id"])
    assert not conversation_belongs_to_customer(conversation_id, customer["id"] + 1)
    assert any(row["id"] == conversation_id for row in get_customer_conversations(customer["id"]))

    save_message(conversation_id, "user", "Private question")
    assert get_conversation_messages(conversation_id, customer_id=customer["id"])
    assert get_conversation_messages(conversation_id, customer_id=customer["id"] + 1) == []
    update_conversation(conversation_id, title="Blocked update", customer_id=customer["id"] + 1)
    with get_connection() as conn:
        title = conn.execute("SELECT title FROM conversations WHERE id = ?", (conversation_id,)).fetchone()["title"]
    assert title != "Blocked update"

    # Repeated migration/seed calls remain idempotent.
    init_db()
    seed_demo_customers()
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM customers WHERE customer_reference LIKE 'KB-DEMO-%'").fetchone()["n"] == 2


def test_orchestrator_customer_integration_is_optional_and_explicit():
    parameters = signature(run_customer_support).parameters
    assert "customer_id" in parameters
    assert parameters["customer_id"].default is None
