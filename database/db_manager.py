
import sqlite3
import json
import hashlib
import hmac
import secrets
from pathlib import Path
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "chat_history.db"


def hash_demo_value(value):
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()


def hash_demo_pin(pin):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 120_000)
    return f"pbkdf2_sha256$120000${salt.hex()}${digest.hex()}"


def verify_demo_pin(pin, encoded):
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded.split("$", 3)
        candidate = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt_hex), int(rounds))
        return algorithm == "pbkdf2_sha256" and hmac.compare_digest(candidate.hex(), digest_hex)
    except (AttributeError, ValueError):
        return False


def hash_admin_password(password):
    return hash_demo_pin(password)


def verify_admin_password(password, encoded):
    return verify_demo_pin(password, encoded)


def current_timestamp():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_connection():
    """Create and safely close a database connection."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():
    """Create all application database tables."""

    with get_connection() as conn:

        conn.executescript("""

        CREATE TABLE IF NOT EXISTS organisations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            domain TEXT,
            official_website TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organisation_id INTEGER,
            filename TEXT NOT NULL,
            file_hash TEXT NOT NULL UNIQUE,
            file_path TEXT,
            status TEXT DEFAULT 'uploaded',
            metadata_json TEXT,
            uploaded_at TEXT NOT NULL,

            FOREIGN KEY (organisation_id)
                REFERENCES organisations(id)
                ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_reference TEXT NOT NULL UNIQUE,
            account_number_hash TEXT NOT NULL UNIQUE,
            account_number_masked TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            mobile_number_hash TEXT NOT NULL,
            mobile_number_masked TEXT NOT NULL,
            demo_pin_hash TEXT NOT NULL,
            branch_name TEXT NOT NULL,
            branch_code TEXT NOT NULL,
            account_type TEXT NOT NULL,
            account_status TEXT NOT NULL,
            login_enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_reference TEXT NOT NULL UNIQUE,
            customer_id INTEGER NOT NULL,
            conversation_id INTEGER,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'Medium',
            status TEXT NOT NULL DEFAULT 'Open',
            assigned_admin_id INTEGER,
            resolution_remarks TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE RESTRICT,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
            FOREIGN KEY (assigned_admin_id) REFERENCES admins(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS complaint_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            remarks TEXT,
            changed_by_admin_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS system_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS admin_activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT NOT NULL,
            target_type TEXT,
            target_id INTEGER,
            details TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            organisation_id INTEGER,
            title TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,

            FOREIGN KEY (organisation_id)
                REFERENCES organisations(id)
                ON DELETE SET NULL
            ,FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            agent_name TEXT,
            content TEXT NOT NULL,
            metadata_json TEXT,
            created_at TEXT NOT NULL,

            FOREIGN KEY (conversation_id)
                REFERENCES conversations(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS agent_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            agent_name TEXT NOT NULL,
            activity_type TEXT,
            description TEXT,
            input_json TEXT,
            output_json TEXT,
            status TEXT,
            created_at TEXT NOT NULL,

            FOREIGN KEY (conversation_id)
                REFERENCES conversations(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS research_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER,
            organisation_id INTEGER,
            cache_key TEXT NOT NULL,
            search_query TEXT NOT NULL,
            topic TEXT,
            results_json TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT,

            FOREIGN KEY (conversation_id)
                REFERENCES conversations(id)
                ON DELETE SET NULL,

            FOREIGN KEY (organisation_id)
                REFERENCES organisations(id)
                ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            message_id INTEGER,
            rating INTEGER,
            comments TEXT,
            created_at TEXT NOT NULL,

            FOREIGN KEY (conversation_id)
                REFERENCES conversations(id)
                ON DELETE CASCADE,

            FOREIGN KEY (message_id)
                REFERENCES messages(id)
                ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_messages_conversation
        ON messages(conversation_id);

        CREATE INDEX IF NOT EXISTS idx_activity_conversation
        ON agent_activity(conversation_id);

        CREATE INDEX IF NOT EXISTS idx_research_cache
        ON research_history(cache_key, created_at);

        CREATE INDEX IF NOT EXISTS idx_conversation_updated
        ON conversations(updated_at);

        CREATE INDEX IF NOT EXISTS idx_messages_role_created
        ON messages(role, created_at);

        CREATE INDEX IF NOT EXISTS idx_complaints_customer_status
        ON complaints(customer_id, status);

        CREATE INDEX IF NOT EXISTS idx_complaints_created
        ON complaints(created_at);

        """)

        columns = {row["name"] for row in conn.execute("PRAGMA table_info(conversations)")}
        if "customer_id" not in columns:
            conn.execute("ALTER TABLE conversations ADD COLUMN customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL")
        customer_columns = {row["name"] for row in conn.execute("PRAGMA table_info(customers)")}
        if "login_enabled" not in customer_columns:
            conn.execute("ALTER TABLE customers ADD COLUMN login_enabled INTEGER NOT NULL DEFAULT 1")
        complaint_columns = {row["name"] for row in conn.execute("PRAGMA table_info(complaints)")}
        if "response_deadline" not in complaint_columns:
            conn.execute("ALTER TABLE complaints ADD COLUMN response_deadline TEXT")
        if "resolution_deadline" not in complaint_columns:
            conn.execute("ALTER TABLE complaints ADD COLUMN resolution_deadline TEXT")
        if "escalation_level" not in complaint_columns:
            conn.execute("ALTER TABLE complaints ADD COLUMN escalation_level INTEGER NOT NULL DEFAULT 0")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_customer ON conversations(customer_id)")

    print("SQLite database initialized successfully.")


# ============================================================
# ORGANISATION MANAGEMENT
# ============================================================

def create_organisation(
    name,
    domain=None,
    official_website=None,
    metadata=None
):
    with get_connection() as conn:

        cursor = conn.execute(
            """
            INSERT INTO organisations
            (name, domain, official_website, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                name,
                domain,
                official_website,
                json.dumps(metadata or {}),
                current_timestamp()
            )
        )

        return cursor.lastrowid


# ============================================================
# CONVERSATION MANAGEMENT
# ============================================================

def create_conversation(
    title="New Conversation",
    organisation_id=None,
    customer_id=None
):
    timestamp = current_timestamp()

    with get_connection() as conn:

        cursor = conn.execute(
            """
            INSERT INTO conversations
            (
                organisation_id,
                customer_id,
                title,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, 'active', ?, ?)
            """,
            (
                organisation_id,
                customer_id,
                title,
                timestamp,
                timestamp
            )
        )

        return cursor.lastrowid


def update_conversation(conversation_id, title=None, status=None, customer_id=None):

    with get_connection() as conn:

        conn.execute(
            """
            UPDATE conversations
            SET
                title = COALESCE(?, title),
                status = COALESCE(?, status),
                updated_at = ?
            WHERE id = ?
              AND (? IS NULL OR customer_id = ?)
            """,
            (
                title,
                status,
                current_timestamp(),
                conversation_id,
                customer_id,
                customer_id
            )
        )


def list_conversations(limit=50):

    with get_connection() as conn:

        rows = conn.execute(
            """
            SELECT *
            FROM conversations
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

        return [dict(row) for row in rows]


def create_demo_customer(customer_reference, account_number, mobile_number, demo_pin,
                         customer_name, branch_name, branch_code, account_type="Savings",
                         account_status="Active"):
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO customers
            (customer_reference, account_number_hash, account_number_masked,
             customer_name, mobile_number_hash, mobile_number_masked, demo_pin_hash,
             branch_name, branch_code, account_type, account_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (customer_reference, hash_demo_value(account_number),
               "*" * max(0, len(account_number) - 4) + account_number[-4:], customer_name,
               hash_demo_value(mobile_number), "******" + mobile_number[-4:], hash_demo_pin(demo_pin),
               branch_name, branch_code, account_type, account_status, current_timestamp()))
        return cursor.lastrowid


def authenticate_customer(account_number, mobile_number, demo_pin):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM customers WHERE login_enabled = 1 AND account_number_hash = ? AND mobile_number_hash = ?",
                           (hash_demo_value(account_number), hash_demo_value(mobile_number))).fetchone()
    if not row or not verify_demo_pin(demo_pin, row["demo_pin_hash"]):
        return None
    return dict(row)


def list_customers():
    with get_connection() as conn:
        rows = conn.execute("""SELECT id, customer_reference, account_number_masked,
            customer_name, mobile_number_masked, branch_name, account_type,
            account_status, login_enabled, created_at FROM customers ORDER BY id""").fetchall()
    return [dict(row) for row in rows]


def add_customer_login(customer_reference, account_number, mobile_number, demo_pin,
                       customer_name, branch_name, branch_code, account_type="Savings"):
    return create_demo_customer(customer_reference, account_number, mobile_number, demo_pin,
                                customer_name, branch_name, branch_code, account_type)


def set_customer_login_enabled(customer_id, enabled):
    with get_connection() as conn:
        cursor = conn.execute("UPDATE customers SET login_enabled = ? WHERE id = ?",
                             (1 if enabled else 0, customer_id))
    return cursor.rowcount == 1


def log_admin_activity(admin_id, action, target_type=None, target_id=None, details=None):
    """Record a non-sensitive administrative action for accountability."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO admin_activity_logs "
            "(admin_id, action, target_type, target_id, details, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (admin_id, action, target_type, target_id, details, current_timestamp()),
        )


def list_admin_activity_logs(limit=100):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, admin_id, action, target_type, target_id, details, created_at "
            "FROM admin_activity_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


COMPLAINT_STATUSES = ("Open", "In Progress", "Awaiting Customer", "Resolved", "Closed")


def _get_sla_settings_conn(conn, priority):
    defaults = {"initial_response_hours": 24, "resolution_hours": 72}
    rows = conn.execute("SELECT setting_key, setting_value FROM system_settings WHERE setting_key LIKE ?",
                        (f"sla_{priority.casefold()}_%",)).fetchall()
    for row in rows:
        if row["setting_key"].endswith("initial_response_hours"):
            defaults["initial_response_hours"] = int(row["setting_value"])
        if row["setting_key"].endswith("resolution_hours"):
            defaults["resolution_hours"] = int(row["setting_value"])
    return defaults


def set_sla_setting(priority, initial_response_hours, resolution_hours):
    now = current_timestamp()
    with get_connection() as conn:
        for suffix, value in (("initial_response_hours", initial_response_hours), ("resolution_hours", resolution_hours)):
            conn.execute("INSERT INTO system_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?) ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value, updated_at = excluded.updated_at",
                         (f"sla_{priority.casefold()}_{suffix}", str(int(value)), now))


def complaint_is_overdue(complaint):
    if complaint.get("status") in ("Resolved", "Closed"):
        return False
    deadline = complaint.get("resolution_deadline")
    if not deadline:
        return False
    try:
        return datetime.now(timezone.utc) > datetime.fromisoformat(deadline)
    except ValueError:
        return False


def create_complaint(customer_id, category, description, conversation_id=None, priority="Medium"):
    timestamp = current_timestamp()
    with get_connection() as conn:
        sla = _get_sla_settings_conn(conn, priority)
        response_deadline = (datetime.now(timezone.utc) + timedelta(hours=sla["initial_response_hours"])).isoformat()
        resolution_deadline = (datetime.now(timezone.utc) + timedelta(hours=sla["resolution_hours"])).isoformat()
        cursor = conn.execute("""INSERT INTO complaints
            (complaint_reference, customer_id, conversation_id, category, description, priority, status, created_at, updated_at, response_deadline, resolution_deadline)
            VALUES (?, ?, ?, ?, ?, ?, 'Open', ?, ?, ?, ?)""",
            ("PENDING", customer_id, conversation_id, category, description, priority, timestamp, timestamp, response_deadline, resolution_deadline))
        complaint_id = cursor.lastrowid
        reference = f"KBL-CMP-{datetime.now(timezone.utc).year}-{complaint_id:06d}"
        conn.execute("UPDATE complaints SET complaint_reference = ? WHERE id = ?", (reference, complaint_id))
    return complaint_id, reference


def get_customer_complaints(customer_id):
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM complaints WHERE customer_id = ? ORDER BY created_at DESC", (customer_id,)).fetchall()
    return [dict(row) for row in rows]


def list_complaints(status=None, category=None):
    clauses, params = [], []
    if status:
        clauses.append("status = ?"); params.append(status)
    if category:
        clauses.append("category = ?"); params.append(category)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_connection() as conn:
        rows = conn.execute(f"SELECT * FROM complaints{where} ORDER BY created_at DESC", params).fetchall()
    return [dict(row) for row in rows]


def update_complaint_status(complaint_id, new_status, admin_id=None, remarks=None):
    if new_status not in COMPLAINT_STATUSES:
        raise ValueError("Invalid complaint status")
    with get_connection() as conn:
        row = conn.execute("SELECT status FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
        if not row:
            return False
        timestamp = current_timestamp()
        resolved_at = timestamp if new_status in ("Resolved", "Closed") else None
        conn.execute("UPDATE complaints SET status = ?, resolution_remarks = COALESCE(?, resolution_remarks), updated_at = ?, resolved_at = COALESCE(?, resolved_at) WHERE id = ?",
                     (new_status, remarks, timestamp, resolved_at, complaint_id))
        conn.execute("INSERT INTO complaint_history (complaint_id, old_status, new_status, remarks, changed_by_admin_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                     (complaint_id, row["status"], new_status, remarks, admin_id, timestamp))
        if admin_id is not None:
            conn.execute("INSERT INTO admin_activity_logs (admin_id, action, target_type, target_id, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                         (admin_id, "complaint_status_updated", "complaint", complaint_id,
                          f"status={new_status}", timestamp))
    return True


def get_complaint_history(complaint_id):
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM complaint_history WHERE complaint_id = ? ORDER BY created_at ASC, id ASC", (complaint_id,)).fetchall()
    return [dict(row) for row in rows]


def get_customer_conversations(customer_id, limit=50):
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM conversations WHERE customer_id = ? ORDER BY updated_at DESC LIMIT ?",
                           (customer_id, limit)).fetchall()
    return [dict(row) for row in rows]


def conversation_belongs_to_customer(conversation_id, customer_id):
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM conversations WHERE id = ? AND customer_id = ?",
                           (conversation_id, customer_id)).fetchone()
    return row is not None


def seed_demo_customers():
    init_db()
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM customers LIMIT 1").fetchone():
            return
    create_demo_customer("KB-DEMO-001", "123456789012", "9876543210", "2468",
                         "Aarav Kumar", "Bengaluru Main Branch", "KB001")
    create_demo_customer("KB-DEMO-002", "123456789013", "9876543211", "1357",
                         "Diya Sharma", "Mangaluru Branch", "KB002")


def seed_initial_admin():
    """Create the initial admin only from environment-provided credentials."""
    import os
    username = os.getenv("ADMIN_USERNAME")
    password = os.getenv("ADMIN_PASSWORD")
    if not username or not password:
        return False
    init_db()
    with get_connection() as conn:
        existing = conn.execute("SELECT 1 FROM admins WHERE username = ?", (username.strip(),)).fetchone()
        if existing:
            conn.execute("UPDATE admins SET password_hash = ? WHERE username = ?",
                         (hash_admin_password(password), username.strip()))
            return True
        conn.execute("INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)",
                     (username.strip(), hash_admin_password(password), current_timestamp()))
    return True


def authenticate_admin(username, password):
    with get_connection() as conn:
        row = conn.execute("SELECT id, username, password_hash FROM admins WHERE username = ?",
                           (username.strip(),)).fetchone()
    if not row or not verify_admin_password(password, row["password_hash"]):
        return None
    return {"id": row["id"], "username": row["username"], "role": "admin"}


# ============================================================
# MESSAGE MANAGEMENT
# ============================================================

def save_message(
    conversation_id,
    role,
    content,
    agent_name=None,
    metadata=None
):
    with get_connection() as conn:

        cursor = conn.execute(
            """
            INSERT INTO messages
            (
                conversation_id,
                role,
                agent_name,
                content,
                metadata_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                role,
                agent_name,
                content,
                json.dumps(metadata or {}),
                current_timestamp()
            )
        )

        conn.execute(
            """
            UPDATE conversations
            SET updated_at = ?
            WHERE id = ?
            """,
            (current_timestamp(), conversation_id)
        )

        return cursor.lastrowid


def update_message_metadata(message_id, metadata):
    with get_connection() as conn:
        conn.execute("UPDATE messages SET metadata_json = ? WHERE id = ?",
                     (json.dumps(metadata or {}), message_id))


def get_conversation_messages(conversation_id, customer_id=None):

    with get_connection() as conn:

        rows = conn.execute(
            """
            SELECT *
            FROM messages
            WHERE conversation_id = ?
              AND (? IS NULL OR EXISTS (
                  SELECT 1 FROM conversations c
                  WHERE c.id = messages.conversation_id
                    AND c.customer_id = ?
              ))
            ORDER BY created_at ASC, id ASC
            """,
            (conversation_id, customer_id, customer_id)
        ).fetchall()

        return [dict(row) for row in rows]


# ============================================================
# AGENT ACTIVITY MANAGEMENT
# ============================================================

def log_agent_activity(
    conversation_id,
    agent_name,
    activity_type,
    description=None,
    input_data=None,
    output_data=None,
    status="completed"
):
    with get_connection() as conn:

        cursor = conn.execute(
            """
            INSERT INTO agent_activity
            (
                conversation_id,
                agent_name,
                activity_type,
                description,
                input_json,
                output_json,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                agent_name,
                activity_type,
                description,
                json.dumps(input_data) if input_data is not None else None,
                json.dumps(output_data) if output_data is not None else None,
                status,
                current_timestamp()
            )
        )

        return cursor.lastrowid


# ============================================================
# WEB RESEARCH HISTORY
# ============================================================

def save_research(
    cache_key,
    search_query,
    results,
    organisation_id=None,
    conversation_id=None,
    topic=None,
    expires_at=None
):
    with get_connection() as conn:

        cursor = conn.execute(
            """
            INSERT INTO research_history
            (
                conversation_id,
                organisation_id,
                cache_key,
                search_query,
                topic,
                results_json,
                created_at,
                expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                organisation_id,
                cache_key,
                search_query,
                topic,
                json.dumps(results),
                current_timestamp(),
                expires_at
            )
        )

        return cursor.lastrowid


def get_cached_research(cache_key):

    with get_connection() as conn:

        row = conn.execute(
            """
            SELECT *
            FROM research_history
            WHERE cache_key = ?
              AND (
                  expires_at IS NULL
                  OR expires_at > ?
              )
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (cache_key, current_timestamp())
        ).fetchone()

        if row is None:
            return None

        result = dict(row)
        result["results"] = json.loads(
            result.pop("results_json") or "[]"
        )

        return result


# ============================================================
# CUSTOMER FEEDBACK
# ============================================================

def save_feedback(
    conversation_id,
    rating,
    comments=None,
    message_id=None
):
    with get_connection() as conn:

        cursor = conn.execute(
            """
            INSERT INTO feedback
            (
                conversation_id,
                message_id,
                rating,
                comments,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                message_id,
                rating,
                comments,
                current_timestamp()
            )
        )

        return cursor.lastrowid


def get_or_create_organisation(
    name,
    domain=None,
    official_website=None,
    metadata=None
):
    """Find an existing organisation or create a new one."""

    with get_connection() as conn:

        existing = conn.execute(
            """
            SELECT id, metadata_json
            FROM organisations
            WHERE name = ? COLLATE NOCASE
            LIMIT 1
            """,
            (name.strip(),)
        ).fetchone()

        if existing:
            org_id = existing["id"]

            old_metadata = json.loads(
                existing["metadata_json"] or "{}"
            )

            old_metadata.update(metadata or {})

            conn.execute(
                """
                UPDATE organisations
                SET
                    domain = COALESCE(domain, ?),
                    official_website = COALESCE(
                        official_website, ?
                    ),
                    metadata_json = ?
                WHERE id = ?
                """,
                (
                    domain,
                    official_website,
                    json.dumps(old_metadata),
                    org_id
                )
            )

            return org_id

        cursor = conn.execute(
            """
            INSERT INTO organisations
            (
                name,
                domain,
                official_website,
                metadata_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                name.strip(),
                domain,
                official_website,
                json.dumps(metadata or {}),
                current_timestamp()
            )
        )

        return cursor.lastrowid


def register_document(
    filename,
    file_hash,
    file_path=None,
    organisation_id=None,
    metadata=None
):
    """Register a document and return its database ID."""

    with get_connection() as conn:

        existing = conn.execute(
            """
            SELECT id
            FROM documents
            WHERE file_hash = ?
            """,
            (file_hash,)
        ).fetchone()

        if existing:
            document_id = existing["id"]

            conn.execute(
                """
                UPDATE documents
                SET
                    organisation_id = COALESCE(
                        ?, organisation_id
                    ),
                    file_path = COALESCE(?, file_path),
                    metadata_json = ?,
                    status = 'analysed'
                WHERE id = ?
                """,
                (
                    organisation_id,
                    str(file_path) if file_path else None,
                    json.dumps(metadata or {}),
                    document_id
                )
            )

            return document_id


        cursor = conn.execute(
            """
            INSERT INTO documents
            (
                organisation_id,
                filename,
                file_hash,
                file_path,
                status,
                metadata_json,
                uploaded_at
            )
            VALUES (?, ?, ?, ?, 'analysed', ?, ?)
            """,
            (
                organisation_id,
                filename,
                file_hash,
                str(file_path) if file_path else None,
                json.dumps(metadata or {}),
                current_timestamp()
            )
        )

        return cursor.lastrowid


def list_organisation_documents(organisation_id):
    with get_connection() as conn:
        rows = conn.execute("""SELECT id, filename, file_path, status, metadata_json,
            uploaded_at FROM documents WHERE organisation_id = ? ORDER BY uploaded_at DESC""",
                           (organisation_id,)).fetchall()
    return [dict(row) for row in rows]


def mark_document_deleted(document_id):
    with get_connection() as conn:
        cursor = conn.execute("UPDATE documents SET status = 'deleted' WHERE id = ?", (document_id,))
    return cursor.rowcount == 1



# ============================================================
# INITIALIZE DATABASE
# ============================================================

if __name__ == "__main__":
    init_db()
