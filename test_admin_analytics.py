from datetime import date

from database.admin_analytics import analytics_summary, classify_customer_signals, classify_query, query_records
from database.db_manager import create_conversation, init_db, save_message, seed_demo_customers


def test_service_and_complaint_classification_is_not_all_complaints():
    assert classify_query("How do I open a savings account?")[0] == "Account Opening"
    assert classify_query("What is the UPI transfer limit?")[1] == "General Enquiry"
    assert classify_query("My debit card transaction failed")[1] == "Complaint"
    assert classify_query("Something unrelated")[0] == "Other / Unclassified"
    assert classify_customer_signals("My UPI transaction failed urgently")["priority_suggestion"] == "High"
    assert classify_customer_signals("Thank you for the good service")["sentiment"] == "Positive"


def test_analytics_reads_actual_messages_and_preserves_unclassified():
    init_db(); seed_demo_customers()
    with __import__("database.db_manager", fromlist=["authenticate_customer"]).get_connection() as conn:
        customer = conn.execute("SELECT id FROM customers LIMIT 1").fetchone()
    conversation = create_conversation("Analytics test", customer_id=customer["id"])
    save_message(conversation, "user", "How do I open a savings account?", metadata={"service": "Account Opening", "query_type": "General Enquiry", "issue": "General enquiry"})
    save_message(conversation, "user", "Unclassified historical question")
    summary = analytics_summary(date.today(), date.today())
    assert summary["total"] >= 2
    assert summary["service_counts"].get("Account Opening", 0) >= 1
    assert any(row["service"] == "Other / Unclassified" for row in query_records(date.today(), date.today()))
