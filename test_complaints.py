from database.db_manager import (
    COMPLAINT_STATUSES, authenticate_customer, create_complaint,
    get_complaint_history, get_customer_complaints, init_db,
    seed_demo_customers, update_complaint_status,
)


def test_complaint_registration_status_history_and_customer_isolation():
    init_db(); seed_demo_customers()
    customer = authenticate_customer("123456789012", "9876543210", "2468")
    assert customer is not None
    complaint_id, reference = create_complaint(customer["id"], "Debit Card", "The card failed twice.")
    assert reference.startswith("KBL-CMP-")
    assert get_customer_complaints(customer["id"])[0]["id"] == complaint_id
    assert get_customer_complaints(customer["id"] + 99999) == []
    assert update_complaint_status(complaint_id, "In Progress", admin_id=None, remarks="Under review")
    assert update_complaint_status(complaint_id, "Resolved", admin_id=None, remarks="Resolved for testing")
    history = get_complaint_history(complaint_id)
    assert [entry["new_status"] for entry in history] == ["In Progress", "Resolved"]
    assert set(COMPLAINT_STATUSES) == {"Open", "In Progress", "Awaiting Customer", "Resolved", "Closed"}
