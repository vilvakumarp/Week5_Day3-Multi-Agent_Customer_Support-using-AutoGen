
import json

from database.db_manager import get_connection


ORG_ID = 2

with get_connection() as conn:

    row = conn.execute(
        """
        SELECT id, name, metadata_json
        FROM organisations
        WHERE id = ?
        """,
        (ORG_ID,)
    ).fetchone()

    if not row:
        raise ValueError("Organisation not found.")

    metadata = json.loads(row["metadata_json"] or "{}")

    # Correct and enrich organisation metadata.
    metadata.update({
        "organisation_name": "Karnataka Bank",
        "industry": "Banking",
        "organisation_type": "Bank",
        "institution_category": "Scheduled Commercial Bank",
        "bank_category": "Private Sector Bank",
        "regulator": "Reserve Bank of India",
        "official_website": "https://www.karnatakabank.bank.in",
        "classification_source": (
            "https://systemhealth.rbi.org.in/"
            "Scripts/bs_viewcontent.aspx_Id%3D3657.html"
        ),
        "classification_verified_on": "2026-11-01"
    })

    conn.execute(
        """
        UPDATE organisations
        SET metadata_json = ?
        WHERE id = ?
        """,
        (
            json.dumps(metadata, ensure_ascii=False),
            ORG_ID
        )
    )

    print("Organisation metadata updated successfully.")
    print(json.dumps(metadata, indent=4, ensure_ascii=False))
