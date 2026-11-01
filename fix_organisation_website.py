
from database.db_manager import get_connection

with get_connection() as conn:

    conn.execute("""
        UPDATE organisations
        SET official_website = ?
        WHERE id = ?
    """, (
        "https://www.karnatakabank.bank.in",
        2
    ))

    conn.commit()

    row = conn.execute("""
        SELECT id, name, official_website
        FROM organisations
        WHERE id = 2
    """).fetchone()

    print(dict(row))

print("Organisation website updated.")
