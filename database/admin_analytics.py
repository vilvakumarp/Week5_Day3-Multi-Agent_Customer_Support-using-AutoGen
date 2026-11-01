import json
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .db_manager import get_connection

SERVICES = [
    "Account Opening", "Account Closure", "Savings Account", "Current Account",
    "Debit Card", "Credit Card", "Internet Banking", "Mobile Banking", "UPI",
    "Fund Transfer", "NEFT / RTGS / IMPS", "Loan Services", "Fixed Deposits",
    "Customer Complaints", "Other / Unclassified",
]


def format_timestamp(value):
    """Format stored UTC timestamps for readable India-local display."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(ZoneInfo("Asia/Kolkata"))
        return parsed.strftime("%d %b %Y, %I:%M %p")
    except (AttributeError, TypeError, ValueError):
        return str(value)

COMPLAINT_TERMS = ("complaint", "failed", "failure", "delay", "delayed", "not received", "issue", "problem", "unable", "blocked")


def classify_query(question, routing=None):
    text = (question or "").casefold()
    intent = str((routing or {}).get("intent", "")).casefold()
    topic = str((routing or {}).get("topic", "")).casefold()
    combined = f"{text} {intent} {topic}"
    rules = [
        ("Account Opening", ("open account", "open a ", "account opening", "new account")),
        ("Account Closure", ("close account", "account closure")),
        ("Savings Account", ("savings account", "saving account")),
        ("Current Account", ("current account",)),
        ("Debit Card", ("debit card", "atm card")),
        ("Credit Card", ("credit card",)),
        ("Internet Banking", ("internet banking", "net banking")),
        ("Mobile Banking", ("mobile banking", "mobile app")),
        ("UPI", ("upi",)),
        ("NEFT / RTGS / IMPS", ("neft", "rtgs", "imps")),
        ("Fund Transfer", ("fund transfer", "transfer money", "bank transfer")),
        ("Loan Services", ("loan", "emi")),
        ("Fixed Deposits", ("fixed deposit", "fd", "term deposit")),
        ("Customer Complaints", ("complaint", "grievance", "escalat")),
    ]
    service = next((name for name, terms in rules if any(term in combined for term in terms)), "Other / Unclassified")
    is_complaint = service == "Customer Complaints" or any(term in text for term in COMPLAINT_TERMS)
    issue = "General enquiry"
    issue_rules = [("Failed transactions", ("failed transaction", "transaction failed")),
                   ("Delayed refunds", ("refund", "reversal")),
                   ("Account access problems", ("unable to login", "access", "locked")),
                   ("Debit card issues", ("debit card", "atm")),
                   ("Mobile banking problems", ("mobile banking", "mobile app")),
                   ("Loan processing delays", ("loan", "processing delay")),
                   ("Service request delays", ("service request", "delayed", "delay"))]
    if is_complaint:
        issue = next((name for name, terms in issue_rules if any(term in text for term in terms)), "Other complaint")
    return service, "Complaint" if is_complaint else "General Enquiry", issue


def classify_customer_signals(question):
    text = (question or "").casefold()
    highly_dissatisfied = ("urgent", "legal action", "fraud", "unauthorised", "unacceptable")
    negative = ("failed", "delay", "delayed", "problem", "issue", "complaint", "unable")
    positive = ("thank", "thanks", "appreciate", "good service")
    if any(term in text for term in highly_dissatisfied):
        sentiment, priority = "Highly dissatisfied", "High"
    elif any(term in text for term in negative):
        sentiment, priority = "Negative", "Medium"
    elif any(term in text for term in positive):
        sentiment, priority = "Positive", "Low"
    else:
        sentiment, priority = "Neutral", "Low"
    issue_key = " ".join(text.split())[:120]
    return {"sentiment": sentiment, "priority_suggestion": priority, "issue_key": issue_key}


def _where(start=None, end=None):
    clauses, params = ["m.role = 'user'"], []
    local_zone = ZoneInfo("Asia/Kolkata")
    if start:
        local_start = datetime.combine(start, datetime.min.time(), tzinfo=local_zone)
        clauses.append("m.created_at >= ?"); params.append(local_start.astimezone(timezone.utc).isoformat())
    if end:
        local_end = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=local_zone)
        clauses.append("m.created_at < ?"); params.append(local_end.astimezone(timezone.utc).isoformat())
    return " AND ".join(clauses), params


def query_records(start=None, end=None):
    where, params = _where(start, end)
    with get_connection() as conn:
        rows = conn.execute(f"""SELECT m.id AS message_id, m.created_at, m.content, m.metadata_json,
            m.conversation_id, c.customer_id, c.title, cu.customer_reference FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            LEFT JOIN customers cu ON cu.id = c.customer_id
            WHERE {where} ORDER BY m.created_at DESC""", params).fetchall()
    records = []
    for row in rows:
        metadata = json.loads(row["metadata_json"] or "{}")
        service, query_type, issue = metadata.get("service"), metadata.get("query_type"), metadata.get("issue")
        if not service or not query_type:
            service, query_type, issue = classify_query(row["content"])
        records.append({**dict(row), "service": service, "query_type": query_type, "issue": issue})
    return records


def analytics_summary(start=None, end=None):
    records = query_records(start, end)
    service_counts = Counter(r["service"] for r in records)
    complaint_counts = Counter(r["service"] for r in records if r["query_type"] == "Complaint")
    issue_counts = Counter(r["issue"] for r in records if r["query_type"] == "Complaint")
    with get_connection() as conn:
        registered_customers = conn.execute("SELECT COUNT(*) AS n FROM customers").fetchone()["n"]
        active_conversations = conn.execute("SELECT COUNT(*) AS n FROM conversations WHERE status = 'active'").fetchone()["n"]
    return {"total": len(records), "complaints": sum(complaint_counts.values()),
            "registered_customers": registered_customers,
            "active_conversations": active_conversations,
            "service_counts": dict(service_counts), "complaint_counts": dict(complaint_counts),
            "issue_counts": dict(issue_counts), "records": records}


def daily_counts(records):
    return dict(sorted(Counter(r["created_at"][:10] for r in records).items()))
