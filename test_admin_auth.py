from database.db_manager import authenticate_admin, authenticate_customer, init_db, seed_initial_admin, add_customer_login, set_customer_login_enabled, log_admin_activity, list_admin_activity_logs, create_complaint, update_complaint_status
from uuid import uuid4


def test_admin_seed_login_and_invalid_credentials(monkeypatch):
    init_db()
    monkeypatch.setenv("ADMIN_USERNAME", "demo-admin-test")
    monkeypatch.setenv("ADMIN_PASSWORD", "demo-password-test")
    seed_initial_admin()
    admin = authenticate_admin("demo-admin-test", "demo-password-test")
    assert admin and admin["role"] == "admin"
    assert authenticate_admin("demo-admin-test", "wrong-password") is None
    assert authenticate_admin("other-user", "demo-password-test") is None


def test_admin_can_add_disable_and_reenable_customer_login():
    init_db()
    suffix = uuid4().hex[:6]
    account, mobile = "1234" + suffix, "9876" + suffix[:6]
    customer_id = add_customer_login("KB-ACCESS-" + suffix, account, mobile, "8642",
                                    "Access Test", "Test Branch", "KBT")
    assert authenticate_customer(account, mobile, "8642") is not None
    assert set_customer_login_enabled(customer_id, False)
    assert authenticate_customer(account, mobile, "8642") is None
    assert set_customer_login_enabled(customer_id, True)
    assert authenticate_customer(account, mobile, "8642") is not None


def test_admin_activity_log_excludes_credentials_and_tracks_actions():
    init_db()
    suffix = uuid4().hex[:6]
    monkey_admin = add_customer_login("KB-AUDIT-" + suffix, "2234" + suffix, "6677" + suffix[:6], "8642", "Audit Test", "Test Branch", "KBA")
    log_admin_activity(1, "customer_login_disabled", "customer", monkey_admin)
    entries = list_admin_activity_logs(10)
    entry = next(item for item in entries if item["target_id"] == monkey_admin)
    assert entry["action"] == "customer_login_disabled"
    assert "8642" not in (entry["details"] or "")


def test_complaint_status_change_creates_admin_audit_entry():
    init_db()
    suffix = uuid4().hex[:6]
    customer_id = add_customer_login("KB-CMP-AUDIT-" + suffix, "3344" + suffix, "7788" + suffix[:6], "9753", "Complaint Audit", "Test Branch", "KBC")
    complaint_id, _ = create_complaint(customer_id, "Debit Card", "Card issue")
    assert update_complaint_status(complaint_id, "In Progress", admin_id=1, remarks="Reviewed")
    entry = next(item for item in list_admin_activity_logs(20) if item["target_id"] == complaint_id)
    assert entry["action"] == "complaint_status_updated"
    assert entry["details"] == "status=In Progress"
