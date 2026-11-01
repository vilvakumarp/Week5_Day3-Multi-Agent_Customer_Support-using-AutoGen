import asyncio
import html
import hashlib
import csv
import io
import textwrap
import importlib
import math
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import streamlit as st
try:
    px = importlib.import_module("plotly.express")
except ImportError:
    px = None
try:
    import altair as alt
except ImportError:
    alt = None
from database.db_manager import authenticate_admin, authenticate_customer, conversation_belongs_to_customer, get_connection, get_conversation_messages, get_customer_conversations, init_db, seed_demo_customers, seed_initial_admin, list_customers, add_customer_login, set_customer_login_enabled, log_admin_activity, list_organisation_documents, register_document, mark_document_deleted, create_complaint, get_customer_complaints, list_complaints, update_complaint_status, complaint_is_overdue, COMPLAINT_STATUSES, update_conversation, save_feedback
from database.admin_analytics import analytics_summary, SERVICES, daily_counts, format_timestamp
from orchestrator import run_customer_support
from rag.vector_store import index_document, delete_document_knowledge

SUPPORT_AGENT_NAME = "Sevaki"
ADMIN_SESSION_DURATION = timedelta(minutes=30)
ADMIN_MAX_LOGIN_FAILURES = 5

def get_karnataka_bank_id():
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM organisations WHERE name = ? COLLATE NOCASE LIMIT 1", ("Karnataka Bank",)).fetchone()
    return row["id"] if row else None

def clear_login():
    st.session_state.pop("customer", None)
    st.session_state.pop("conversation_id", None)


def clear_admin_session():
    st.session_state.pop("admin", None)
    st.session_state.pop("admin_authenticated_at", None)


def admin_session_expired():
    authenticated_at = st.session_state.get("admin_authenticated_at")
    return not isinstance(authenticated_at, datetime) or datetime.now(timezone.utc) - authenticated_at >= ADMIN_SESSION_DURATION


def apply_bank_theme():
    st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #fffafd 0%, #fceafa 52%, #efd8ef 100%); }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #9D0081 0%, #83106f 55%, #5d1559 100%); }
    [data-testid="stSidebar"] > div:first-child { width: 300px; }
    .main .block-container { max-width: none; margin-left: 0; margin-right: 0; padding: 2rem 2.5rem 3rem 2.5rem; }
    [data-testid="stMainBlockContainer"] { max-width: none !important; width: 100% !important; padding-left: 2rem !important; padding-right: 2rem !important; }
    [data-testid="stMainBlockContainer"] > div { max-width: none !important; }
    [data-testid="stDataFrame"] { width: 100%; }
    [data-testid="stTable"] { display: flex; justify-content: center; }
    [data-testid="stTable"] table { width: auto !important; min-width: 420px; }
    [data-testid="stTable"] th, [data-testid="stTable"] td { text-align: center !important; white-space: nowrap; }
    .compact-table-wrap { display: flex; justify-content: center; width: 100%; margin: 0.5rem 0 1rem; }
    .compact-table { width: auto; border-collapse: separate; border-spacing: 0; border: 1px solid #d8c8df; border-radius: 10px; overflow: hidden; background: rgba(255,255,255,.55); }
    .compact-table th, .compact-table td { padding: 8px 18px; text-align: center; white-space: nowrap; border-right: 1px solid #e2d8e7; border-bottom: 1px solid #e2d8e7; }
    .compact-table th { color: #6d6680; font-weight: 600; background: rgba(255,255,255,.65); }
    .compact-table tr:last-child td { border-bottom: 0; }
    .compact-table th:last-child, .compact-table td:last-child { border-right: 0; }
    [data-testid="stSidebar"] * { color: #ffffff !important; }
    [data-testid="stSidebar"] .stButton > button { background: #ffffff !important; color: #4b145c !important; border: 1px solid #ead8ee !important; font-weight: 600; }
    [data-testid="stSidebar"] .stButton > button p,
    [data-testid="stSidebar"] .stButton > button span,
    [data-testid="stSidebar"] .stButton > button div { color: #4b145c !important; }
    [data-testid="stSidebar"] .stButton > button:hover { background: #f7e6f8 !important; color: #4b145c !important; border-color: #a83eae !important; }
    .bank-header { background: #9D0081; color: white; padding: 18px 24px; border-radius: 0 0 14px 14px; margin: -1rem -1rem 1.5rem -1rem; }
    .bank-header h1 { margin: 0; font-size: 2rem; letter-spacing: .2px; }
    .bank-header p { margin: 4px 0 0; color: #d9e8f5; }
    .stButton > button[kind="primary"] { background: #9D0081; border-color: #9D0081; }
    .stButton > button[kind="primary"]:hover { background: #780064; border-color: #780064; }
    [data-testid="stMetric"] { background: white; border: 1px solid #e2e7ee; padding: 12px; border-radius: 12px; box-shadow: 0 2px 8px rgba(16,42,67,.05); }
    </style>
    """, unsafe_allow_html=True)


def render_message_bubble(speaker, content, is_customer=False):
    background = "#f1f3f6" if is_customer else "#e8f1ff"
    border = "#d9dee7" if is_customer else "#c8dcff"
    alignment = "flex-end" if is_customer else "flex-start"
    label_alignment = "right" if is_customer else "left"
    safe_speaker = html.escape(str(speaker))
    safe_content = html.escape(str(content)).replace("\n", "<br>")
    st.markdown(
        f"<div style='display:flex; flex-direction:column; align-items:{alignment}; margin:12px 0 18px 0;'>"
        f"<div style='font-weight:700; margin-bottom:5px; text-align:{label_alignment};'>{safe_speaker}</div>"
        f"<div style='background:{background}; border:1px solid {border}; border-radius:16px; padding:12px 16px; line-height:1.5; max-width:88%;'>{safe_content}</div></div>",
        unsafe_allow_html=True,
    )


def csv_bytes(rows, fields):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def render_compact_table(rows, columns):
    headers = "".join(f"<th>{html.escape(str(label))}</th>" for label, _ in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row.get(key, '')))}</td>" for _, key in columns) + "</tr>"
        for row in rows
    )
    st.markdown(
        f"<div class='compact-table-wrap'><table class='compact-table'><thead><tr>{headers}</tr></thead><tbody>{body}</tbody></table></div>",
        unsafe_allow_html=True,
    )

def login_page():
    apply_bank_theme()
    st.markdown("<div class='bank-header'><h1>Karnataka Bank</h1><p>Your family bank across India · Customer Support Demo</p></div>", unsafe_allow_html=True)
    st.caption("Customer Support Demo — demonstration authentication only")
    mode = st.radio("Login type", ["Customer Login", "Admin Login"], horizontal=True)
    if mode == "Admin Login":
        with st.form("admin_login"):
            username = st.text_input("Administrator username")
            password = st.text_input("Administrator password", type="password")
            submitted = st.form_submit_button("Admin log in", type="primary")
        if submitted:
            if st.session_state.get("admin_login_failures", 0) >= ADMIN_MAX_LOGIN_FAILURES:
                st.error("Administrator login is temporarily locked for this session.")
                return
            admin = authenticate_admin(username, password)
            if admin:
                st.session_state.pop("customer", None)
                st.session_state.pop("conversation_id", None)
                st.session_state.admin = admin
                st.session_state.admin_authenticated_at = datetime.now(timezone.utc)
                st.session_state.admin_login_failures = 0
                st.rerun()
            st.session_state.admin_login_failures = st.session_state.get("admin_login_failures", 0) + 1
            st.error("Invalid administrator credentials.")
        st.info("Administrator access requires ADMIN_USERNAME and ADMIN_PASSWORD.")
        return
    with st.form("customer_login"):
        account = st.text_input("Customer Account Number")
        mobile = st.text_input("Registered Mobile Number")
        pin = st.text_input("Demo PIN", type="password")
        submitted = st.form_submit_button("Log in", type="primary")
    if submitted:
        customer = authenticate_customer(account, mobile, pin)
        if customer:
            st.session_state.pop("admin", None)
            st.session_state.customer = {"id": customer["id"], "name": customer["customer_name"], "account_masked": customer["account_number_masked"], "branch": customer["branch_name"], "account_type": customer["account_type"], "account_status": customer["account_status"]}
            st.rerun()
        st.error("The demo account number, mobile number, or PIN is invalid.")

def customer_dashboard():
    apply_bank_theme()
    customer = st.session_state.customer
    with st.sidebar:
        st.subheader("Karnataka Bank")
        st.write(f"Signed in as **{customer['name']}**")
        st.caption(customer["account_masked"])
        if st.button("Log out"):
            clear_login(); st.rerun()
        st.divider(); st.subheader("Your conversations")
        if st.button("New conversation"):
            st.session_state.conversation_id = None; st.rerun()
        for conversation in get_customer_conversations(customer["id"]):
            label = conversation.get("title") or f"Conversation {conversation['id']}"
            if st.button(label[:36], key=f"conversation_{conversation['id']}"):
                st.session_state.conversation_id = conversation["id"]; st.rerun()
        if st.session_state.get("conversation_id"):
            with st.expander("Rename selected conversation"):
                with st.form("rename_conversation"):
                    new_title = st.text_input("Conversation title")
                    if st.form_submit_button("Save title") and new_title.strip():
                        update_conversation(st.session_state.conversation_id, title=new_title.strip(), customer_id=customer["id"])
                        st.rerun()
    st.markdown(f"<div class='bank-header'><h1>Welcome, {customer['name']}</h1><p>Personal banking support · Secure demo workspace</p></div>", unsafe_allow_html=True)
    st.caption("Demonstration data only; not connected to banking systems.")
    st.subheader(SUPPORT_AGENT_NAME)
    st.success("Ready to help resolve your customer support questions.")
    values = [customer["name"], customer["account_masked"], customer["branch"], customer["account_type"], customer["account_status"]]
    for column, label, value in zip(st.columns(5), ["Customer", "Account", "Branch", "Type", "Status"], values):
        column.metric(label, value)
    conversation_id = st.session_state.get("conversation_id")
    if conversation_id and not conversation_belongs_to_customer(conversation_id, customer["id"]):
        st.session_state.conversation_id = None; conversation_id = None
    for message in get_conversation_messages(conversation_id, customer_id=customer["id"]) if conversation_id else []:
        speaker = customer["name"] if message["role"] == "user" else SUPPORT_AGENT_NAME
        render_message_bubble(speaker, message["content"], message["role"] == "user")
    st.subheader("Formal complaints")
    for complaint in get_customer_complaints(customer["id"]):
        st.write(f"**{complaint['complaint_reference']}** · {complaint['category']} · {complaint['status']} · {format_timestamp(complaint['created_at'])}")
        if complaint.get("resolution_remarks"):
            st.caption(complaint["resolution_remarks"])
    support_mode = st.radio("Support request", ["Ask Sevaki", "Raise a Complaint"], horizontal=True)
    if support_mode == "Raise a Complaint":
        with st.form("raise_complaint"):
            category = st.selectbox("Complaint category", SERVICES)
            description = st.text_area("Describe the complaint")
            submitted = st.form_submit_button("Submit complaint", type="primary")
        if submitted:
            if not description.strip():
                st.error("Please describe the complaint.")
            else:
                _, reference = create_complaint(customer["id"], category, description, conversation_id)
                st.success(f"Complaint submitted. Reference: {reference}")
                st.rerun()
        return
    question = st.chat_input("Ask a question about customer support")
    if not question:
        return
    render_message_bubble(customer["name"], question, is_customer=True)
    organisation_id = get_karnataka_bank_id()
    if not organisation_id:
        st.error("Karnataka Bank organisation data is not available."); return
    progress = st.empty()
    def update_progress(stage, description):
        percent = round(stage * 100 / 6)
        progress.markdown(
            f"<div style='display:flex; flex-direction:column; align-items:flex-start; margin:12px 0 18px 0;'>"
            f"<div style='font-weight:700; margin-bottom:5px;'>Sevaki</div>"
            f"<div style='background:#e8f1ff; border:1px solid #c8dcff; border-radius:16px; padding:12px 16px; line-height:1.5;'>"
            f"<b>{stage}/6</b>&nbsp;&nbsp;<span style='color:#168447; letter-spacing:1px;'>{'█' * stage}</span><span style='color:#aeb8c4;'>{'─' * (6 - stage)}</span>&nbsp;&nbsp;{html.escape(description)}"
            f"<br><small>Progress: {percent}%</small></div></div>",
            unsafe_allow_html=True,
        )
    try:
        result = asyncio.run(run_customer_support(question=question, organisation_id=organisation_id, conversation_id=conversation_id, customer_id=customer["id"], progress_callback=update_progress))
    except Exception as error:
        progress.error("Processing failed. Please try again or contact support."); st.exception(error); return
    progress.markdown(
        "<div style='display:flex; flex-direction:column; align-items:flex-start; margin:12px 0 18px 0;'>"
        "<div style='font-weight:700; margin-bottom:5px;'>Sevaki</div>"
        "<div style='background:#e8f1ff; border:1px solid #c8dcff; border-radius:16px; padding:12px 16px;'>"
        "<b>6/6</b>&nbsp;&nbsp;<span style='color:#168447;'>██████</span>&nbsp;&nbsp;Response ready<br>"
        "<small>Progress: 100%</small></div></div>",
        unsafe_allow_html=True,
    )
    st.session_state.conversation_id = result["conversation_id"]
    render_message_bubble(SUPPORT_AGENT_NAME, result["answer"])
    feedback_cols = st.columns(2)
    if feedback_cols[0].button("Helpful", key=f"helpful_{result['assistant_message_id']}"):
        save_feedback(result["conversation_id"], 1, message_id=result["assistant_message_id"])
        st.toast("Thanks for the feedback.")
    if feedback_cols[1].button("Not helpful", key=f"not_helpful_{result['assistant_message_id']}"):
        save_feedback(result["conversation_id"], 0, message_id=result["assistant_message_id"])
        st.toast("Thanks — this helps us improve.")
    st.rerun()

def admin_dashboard():
    if admin_session_expired():
        clear_admin_session()
        st.warning("Your administrator session expired. Please log in again.")
        st.rerun()
    apply_bank_theme()
    with st.sidebar:
        st.subheader("Karnataka Bank Admin")
        st.caption(st.session_state.admin["username"])
        page = st.radio("Dashboard section", ["Overview", "Service-wise Analytics", "Query Trends & History", "Complaint Management", "Reports", "User Login Access", "Knowledge Management"])
        if st.button("Admin logout"):
            clear_admin_session(); st.rerun()
    st.title(page)
    today = date.today(); selected_range = st.selectbox("Date range", ["Today", "Last 7 days", "Last 30 days", "Last 90 days", "Custom"])
    start, end = today, today
    if selected_range.startswith("Last"):
        start = today - timedelta(days=int(selected_range.split()[1]) - 1)
    elif selected_range == "Custom":
        start = st.date_input("Start date", today - timedelta(days=6)); end = st.date_input("End date", today)
    summary = analytics_summary(start, end)
    cards = st.columns(5)
    cards[0].metric("Total questions", summary["total"])
    cards[1].metric("Classified complaints", summary["complaints"])
    cards[2].metric("Registered customers", summary["registered_customers"])
    cards[3].metric("Active conversations", summary["active_conversations"])
    cards[4].metric("Services represented", len(summary["service_counts"]))
    if page == "Overview":
        st.info("Formal complaint status metrics will appear after the complaint-management phase is implemented.")
    if page in ("Overview", "Service-wise Analytics"):
        if page == "Overview":
            st.subheader("Service-wise analysis")
        if page == "Service-wise Analytics":
            top_services = sorted(summary["service_counts"].items(), key=lambda item: -item[1])[:5]
            st.subheader("Highest-volume services")
            top_columns = st.columns([1, 1.25])
            with top_columns[0]:
                render_compact_table(
                    [{"Rank": index, "Service": service, "Questions": count} for index, (service, count) in enumerate(top_services, start=1)],
                    [("Rank", "Rank"), ("Service", "Service"), ("Questions", "Questions")],
                )
            with top_columns[1]:
                top_pie_rows = [{"Service": service, "Questions": count} for service, count in top_services]
                if px and top_pie_rows:
                    top_pie = px.pie(top_pie_rows, names="Service", values="Questions", hole=0.42, title="Top services share")
                    top_pie.update_layout(height=350, margin={"l": 10, "r": 10, "t": 45, "b": 10})
                    st.plotly_chart(top_pie, use_container_width=True, key=f"top_services_pie_{start}_{end}")
                elif alt and top_pie_rows:
                    top_pie = alt.Chart(alt.Data(values=top_pie_rows)).mark_arc(innerRadius=55).encode(
                        theta=alt.Theta("Questions:Q"),
                        color=alt.Color("Service:N", title="Service"),
                        tooltip=[alt.Tooltip("Service:N", title="Service"), alt.Tooltip("Questions:Q", title="Questions")],
                    ).properties(height=350, title="Top services share")
                    st.altair_chart(top_pie, use_container_width=True, key=f"top_services_pie_fallback_{start}_{end}")
        filtered_service_counts = {service: sum(record["service"] == service for record in summary["records"]) for service in SERVICES}
        service_rows = [{"Service": service, "Display service": "<br>".join(textwrap.wrap(service, width=18)), "Questions": filtered_service_counts[service]} for service in SERVICES]
        service_table_rows = [{"Service": service, "Questions": summary["service_counts"].get(service, 0), "Complaints": summary["complaint_counts"].get(service, 0), "Percentage": round(summary["service_counts"].get(service, 0) * 100 / summary["total"], 1) if summary["total"] else 0} for service in SERVICES]
        chart_rows = service_rows
        axis_max = max(20, int(math.ceil(max((row["Questions"] for row in chart_rows), default=0) / 20) * 20))
        if px and chart_rows:
            service_chart = px.bar(chart_rows, x="Questions", y="Service", text="Questions", hover_name="Service", orientation="h", title=f"Questions by service ({start} to {end})")
            service_chart.update_layout(height=500, margin={"l": 10, "r": 20, "t": 55, "b": 45}, xaxis={"range": [0, axis_max], "dtick": 20, "automargin": True}, yaxis={"automargin": True, "categoryorder": "total ascending"})
            st.plotly_chart(service_chart, use_container_width=True, key=f"service_chart_v2_{page}_{start}_{end}")
            if page == "Overview":
                overview_columns = st.columns(2)
                with overview_columns[0]:
                    comparison_rows = [{"Service": service, "Questions": summary["service_counts"].get(service, 0), "Complaints": summary["complaint_counts"].get(service, 0)} for service in SERVICES if summary["service_counts"].get(service, 0)]
                    comparison_axis_max = max(20, int(math.ceil(max((max(row["Questions"], row["Complaints"]) for row in comparison_rows), default=0) / 20) * 20))
                    comparison_chart = px.bar(comparison_rows, x=["Questions", "Complaints"], y="Service", barmode="group", orientation="h", title="Questions versus complaints")
                    comparison_chart.update_layout(height=430, margin={"l": 10, "r": 10, "t": 55, "b": 45}, xaxis={"range": [0, comparison_axis_max], "dtick": 20, "automargin": True}, yaxis={"automargin": True, "categoryorder": "total ascending"})
                    st.plotly_chart(comparison_chart, use_container_width=True)
                with overview_columns[1]:
                    overview_pie = px.pie(service_rows, names="Service", values="Questions", hole=0.42, title="Question share by service")
                    st.plotly_chart(overview_pie, use_container_width=True)
                    render_compact_table(service_table_rows, [("Service", "Service"), ("Questions", "Questions"), ("Complaints", "Complaints"), ("Percentage", "Percentage")])
                st.subheader("Customer query trend")
                st.line_chart(daily_counts(summary["records"]))
                overview_complaints = []
                for complaint in list_complaints():
                    try:
                        complaint_date = datetime.fromisoformat(complaint["created_at"].replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Kolkata")).date()
                    except (AttributeError, TypeError, ValueError):
                        continue
                    if start <= complaint_date <= end:
                        overview_complaints.append(complaint)
                if overview_complaints and px:
                    overview_status_rows = [{"Status": status, "Complaints": sum(item["status"] == status for item in overview_complaints)} for status in COMPLAINT_STATUSES]
                    overview_status_chart = px.pie(overview_status_rows, names="Status", values="Complaints", hole=0.42, title="Complaint status mix")
                    st.plotly_chart(overview_status_chart, use_container_width=True)
        else:
            if alt:
                st.altair_chart(alt.Chart(alt.Data(values=chart_rows)).mark_bar().encode(
                    x=alt.X("Questions:Q", title="Questions", scale=alt.Scale(domain=[0, axis_max]), axis=alt.Axis(tickMinStep=20, format="d")),
                    y=alt.Y("Service:N", sort="-x", title="Service"),
                    tooltip=[alt.Tooltip("Service:N", title="Service"), alt.Tooltip("Questions:Q", title="Questions")],
                ).properties(height=500, title=f"Questions by service ({start} to {end})"), use_container_width=True, key=f"service_chart_fallback_v2_{page}_{start}_{end}")
            else:
                st.bar_chart(filtered_service_counts)
        if page == "Service-wise Analytics":
            lower_columns = st.columns([1.15, 1])
            with lower_columns[0]:
                if px:
                    pie_chart = px.pie(service_rows, names="Service", values="Questions", hole=0.42, title="Question distribution by service")
                    pie_chart.update_layout(height=500, margin={"l": 10, "r": 10, "t": 55, "b": 10})
                    st.plotly_chart(pie_chart, use_container_width=True, key=f"service_distribution_pie_{start}_{end}")
            with lower_columns[1]:
                render_compact_table(service_table_rows, [("Service", "Service"), ("Questions", "Questions"), ("Complaints", "Complaints"), ("Percentage", "Percentage")])
        elif page not in ("Overview",):
            render_compact_table(service_table_rows, [("Service", "Service"), ("Questions", "Questions"), ("Complaints", "Complaints"), ("Percentage", "Percentage")])
    if page == "Query Trends & History":
        st.subheader("Query trends")
        st.line_chart(daily_counts(summary["records"]))
        trend_rows = [{"Service": service, "Display service": "<br>".join(textwrap.wrap(service, width=18)), "Questions": summary["service_counts"].get(service, 0)} for service in SERVICES]
        trend_axis_max = max(20, int(math.ceil(max((row["Questions"] for row in trend_rows), default=0) / 20) * 20))
        if px and trend_rows:
            trend_chart = px.bar(trend_rows, x="Questions", y="Service", text="Questions", hover_name="Service", orientation="h", title="Questions by service")
            trend_chart.update_layout(height=500, margin={"l": 10, "r": 20, "t": 45, "b": 45}, xaxis={"range": [0, trend_axis_max], "dtick": 20, "automargin": True}, yaxis={"automargin": True, "categoryorder": "total ascending"})
            st.plotly_chart(trend_chart, use_container_width=True)
        else:
            if alt:
                st.altair_chart(alt.Chart(alt.Data(values=trend_rows)).mark_bar().encode(
                    x=alt.X("Questions:Q", title="Questions", scale=alt.Scale(domain=[0, trend_axis_max]), axis=alt.Axis(tickMinStep=20, format="d")),
                    y=alt.Y("Service:N", sort="-x", title="Service"),
                    tooltip=[alt.Tooltip("Service:N", title="Service"), alt.Tooltip("Questions:Q", title="Questions")],
                ).properties(height=500), use_container_width=True)
            else:
                st.bar_chart({service: summary["service_counts"].get(service, 0) for service in SERVICES})
    if page == "Query Trends & History":
        st.subheader("Customer query history")
        search = st.text_input("Search customer questions")
        records = [r for r in summary["records"] if not search or search.casefold() in r["content"].casefold()]
        st.dataframe(
            [{"Date/time": format_timestamp(r["created_at"]), "Customer": r.get("customer_reference") or "Legacy", "Conversation": r["conversation_id"], "Question": r["content"], "Service": r["service"], "Query type": r["query_type"]} for r in records],
            use_container_width=True,
            height=430,
            hide_index=True,
            column_config={
                "Date/time": st.column_config.TextColumn(),
                "Customer": st.column_config.TextColumn(),
                "Conversation": st.column_config.NumberColumn(),
                "Question": st.column_config.TextColumn(),
                "Service": st.column_config.TextColumn(),
                "Query type": st.column_config.TextColumn(),
            },
        )
    if page == "Complaint Management":
        st.subheader("Complaint management")
        st.caption("Review, filter, and update formal complaints from one organised register.")
        all_complaints = list_complaints()
        status_counts = {status: sum(item["status"] == status for item in all_complaints) for status in COMPLAINT_STATUSES}
        completed_count = status_counts["Resolved"] + status_counts["Closed"]
        overdue_count = sum(complaint_is_overdue(item) for item in all_complaints)
        dashboard_cards = st.columns(5)
        dashboard_cards[0].metric("Total complaints", len(all_complaints))
        dashboard_cards[1].metric("Needs attention", status_counts["Open"] + status_counts["In Progress"])
        dashboard_cards[2].metric("Awaiting customer", status_counts["Awaiting Customer"])
        dashboard_cards[3].metric("Resolved / closed", completed_count)
        dashboard_cards[4].metric("Overdue", overdue_count)
        if all_complaints:
            resolution_rate = completed_count * 100 / len(all_complaints)
            st.caption(f"Resolution progress: {resolution_rate:.1f}% of recorded complaints are resolved or closed.")
            if px:
                status_rows = [{"Status": status, "Complaints": count} for status, count in status_counts.items()]
                chart_columns = st.columns(2)
                with chart_columns[0]:
                    status_axis_max = max(20, int(math.ceil(max(status_counts.values(), default=0) / 20) * 20))
                    status_chart = px.bar(status_rows, x="Complaints", y="Status", orientation="h", text="Complaints", title="Complaint status counts")
                    status_chart.update_layout(height=430, margin={"l": 10, "r": 10, "t": 55, "b": 35}, xaxis={"range": [0, status_axis_max], "dtick": 20, "automargin": True}, yaxis={"automargin": True, "categoryorder": "total ascending"})
                    st.plotly_chart(status_chart, use_container_width=True, key=f"complaint_status_bar_{start}_{end}")
                with chart_columns[1]:
                    status_pie = px.pie(status_rows, names="Status", values="Complaints", hole=0.42, title="Complaint status mix")
                    st.plotly_chart(status_pie, use_container_width=True)
            else:
                st.bar_chart(status_counts)
        else:
            st.info("No complaint records are available for the dashboard yet.")
        status_filter = st.selectbox("Filter by status", ["All", *COMPLAINT_STATUSES])
        complaints = list_complaints(None if status_filter == "All" else status_filter)
        table_rows = [{"Reference": item["complaint_reference"], "Category": item["category"], "Priority": item["priority"], "Status": item["status"], "Created": format_timestamp(item["created_at"])} for item in complaints]
        if not complaints:
            st.info("No complaints match the selected filter.")
        else:
            @st.dialog("Complaint details")
            def show_complaint_dialog(complaint):
                st.markdown(f"#### {complaint['complaint_reference']}")
                details = st.columns([1.4, 1, 1.8])
                details[0].markdown(f"**Category**\n\n{complaint['category']}")
                details[1].markdown(f"**Priority**\n\n{complaint['priority']}")
                details[2].markdown(f"**Created**\n\n{format_timestamp(complaint['created_at'])}")
                st.text_area("Complaint description", complaint["description"], disabled=True, key=f"description_{complaint['id']}")
                new_status = st.selectbox("Update status", COMPLAINT_STATUSES, index=COMPLAINT_STATUSES.index(complaint["status"]), key=f"status_{complaint['id']}")
                remarks = st.text_area("Resolution or internal remarks", value=complaint.get("resolution_remarks") or "", key=f"remarks_{complaint['id']}")
                if st.button("Save complaint update", type="primary", key=f"save_complaint_{complaint['id']}"):
                    update_complaint_status(complaint["id"], new_status, st.session_state.admin["id"], remarks)
                    st.rerun()

            st.caption("Click a complaint reference to view details or update its status.")
            header = st.columns([2.8, 2, 1.2, 2, 2.8])
            for column, label in zip(header, ["Reference", "Category", "Priority", "Status", "Created"]):
                column.markdown(f"**{label}**")
            for complaint in complaints:
                row = st.columns([2.8, 2, 1.2, 2, 2.8])
                if row[0].button(complaint["complaint_reference"], key=f"open_complaint_{complaint['id']}"):
                    show_complaint_dialog(complaint)
                row[1].write(complaint["category"])
                row[2].write(complaint["priority"])
                row[3].write(complaint["status"])
                row[4].write(format_timestamp(complaint["created_at"]))
    if page == "Reports":
        st.subheader("Management reports")
        safe_fields = ["created_at", "customer_reference", "conversation_id", "content", "service", "query_type"]
        report_rows = [{"created_at": format_timestamp(row["created_at"]), "customer_reference": row.get("customer_reference") or "Legacy", "conversation_id": row["conversation_id"], "content": row["content"], "service": row["service"], "query_type": row["query_type"]} for row in summary["records"]]
        st.download_button("Download query report (CSV)", csv_bytes(report_rows, safe_fields), "customer_query_report.csv", "text/csv")
        service_rows = [{"service": service, "questions": count, "complaints": summary["complaint_counts"].get(service, 0)} for service, count in sorted(summary["service_counts"].items(), key=lambda item: -item[1])]
        st.download_button("Download service report (CSV)", csv_bytes(service_rows, ["service", "questions", "complaints"]), "service_report.csv", "text/csv")
        complaint_rows = [{"reference": row["complaint_reference"], "category": row["category"], "status": row["status"], "priority": row["priority"], "created_at": format_timestamp(row["created_at"])} for row in list_complaints()]
        st.download_button("Download complaint report (CSV)", csv_bytes(complaint_rows, ["reference", "category", "status", "priority", "created_at"]), "complaint_report.csv", "text/csv")
    if page == "User Login Access":
        st.subheader("Customer login access")
        st.caption("Disabling access preserves the customer record and conversation history.")
        for customer in [item for item in list_customers() if item["login_enabled"]]:
            status = "Enabled" if customer["login_enabled"] else "Disabled"
            left, middle, right = st.columns([3, 2, 1])
            left.write(f"**{customer['customer_name']}** · {customer['customer_reference']} · {customer['account_number_masked']}")
            middle.write(status)
            if right.button("Disable", key=f"access_{customer['id']}"):
                set_customer_login_enabled(customer["id"], False)
                log_admin_activity(st.session_state.admin["id"], "customer_login_disabled", "customer", customer["id"])
                st.rerun()
        disabled_customers = [item for item in list_customers() if not item["login_enabled"]]
        if disabled_customers:
            st.markdown("#### Disabled customers")
            st.caption("Disabled customers cannot log in, but their conversations and complaint history are retained.")
            for customer in disabled_customers:
                left, middle, right = st.columns([3, 2, 1])
                left.write(f"**{customer['customer_name']}** · {customer['customer_reference']} · {customer['account_number_masked']}")
                middle.write("Disabled")
                if right.button("Enable", key=f"access_{customer['id']}"):
                    set_customer_login_enabled(customer["id"], True)
                    log_admin_activity(st.session_state.admin["id"], "customer_login_enabled", "customer", customer["id"])
                    st.rerun()
        with st.expander("Add demo customer login"):
            with st.form("add_customer_login"):
                reference = st.text_input("Customer reference")
                name = st.text_input("Customer name")
                account = st.text_input("Account number")
                mobile = st.text_input("Registered mobile number")
                pin = st.text_input("Demo PIN", type="password")
                branch = st.text_input("Branch name")
                branch_code = st.text_input("Branch code")
                add = st.form_submit_button("Add login")
            if add:
                try:
                    add_customer_login(reference, account, mobile, pin, name, branch, branch_code)
                    st.success("Customer login added.")
                    st.rerun()
                except Exception:
                    st.error("Could not add the customer login. Check that the reference and account are unique.")
    if page == "Knowledge Management":
        st.subheader("Organisation knowledge base")
        st.caption("PDFs are embedded into the persistent ChromaDB knowledge base for Karnataka Bank support.")
        organisation_id = get_karnataka_bank_id()
        upload = st.file_uploader("Add a PDF to knowledge", type=["pdf"])
        if upload and st.button("Upload and index PDF", type="primary"):
            upload_dir = Path(__file__).resolve().parent / "data" / "uploaded_pdfs"
            upload_dir.mkdir(parents=True, exist_ok=True)
            destination = upload_dir / Path(upload.name).name
            destination.write_bytes(upload.getvalue())
            file_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
            try:
                document_id = register_document(upload.name, file_hash, destination, organisation_id, {"source": "admin_upload"})
                knowledge_progress = st.empty()
                def update_knowledge_progress(percent, description):
                    filled = round(percent / 10)
                    knowledge_progress.markdown(
                        f"**Knowledge base update**  `{('█' * filled) + ('─' * (10 - filled))}` **{percent}%**  {description}"
                    )
                result = index_document(destination, organisation_id, document_id, update_knowledge_progress)
                st.success(f"Indexed {upload.name}: {result['indexed_chunks']} chunks added.")
                st.rerun()
            except Exception as error:
                st.error(f"The PDF could not be indexed: {error}")
        st.subheader("Indexed documents")
        for document in list_organisation_documents(get_karnataka_bank_id()):
            if document["status"] == "deleted":
                continue
            left, status_col, date_col, right = st.columns([4.5, 1.2, 2.2, 1])
            left.write(f"**{document['filename']}**")
            status_col.write(document["status"])
            date_col.markdown(f"<span style='white-space:nowrap;'>uploaded {format_timestamp(document['uploaded_at'])}</span>", unsafe_allow_html=True)
            if right.button("Delete knowledge", key=f"delete_doc_{document['id']}"):
                delete_document_knowledge(document["id"])
                mark_document_deleted(document["id"])
                st.success("Document removed from the knowledge base. The uploaded file was retained.")
                st.rerun()

init_db(); seed_demo_customers(); seed_initial_admin()
if "admin" in st.session_state:
    admin_dashboard()
elif "customer" in st.session_state:
    customer_dashboard()
else:
    login_page()
