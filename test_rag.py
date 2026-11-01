
import sqlite3
import hashlib
from pathlib import Path

from rag.vector_store import (
    index_document,
    get_collection_count,
    get_organisation_document_count
)

from rag.retrieval import (
    search_knowledge_base,
    format_retrieved_context
)


BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "chat_history.db"

PDF_PATH = (
    BASE_DIR
    / "data"
    / "uploaded_pdfs"
    / "standard-operating-procedure-for-handling-customer.pdf"
)


def main():

    print("\n1. Checking registered document...")

    file_hash = hashlib.sha256(
        PDF_PATH.read_bytes()
    ).hexdigest()

    with sqlite3.connect(DB_PATH) as conn:

        conn.row_factory = sqlite3.Row

        document = conn.execute(
            """
            SELECT *
            FROM documents
            WHERE file_hash = ?
            """,
            (file_hash,)
        ).fetchone()

    if document is None:
        raise ValueError(
            "Document is not registered in SQLite. "
            "Run test_document_intelligence.py first."
        )

    organisation_id = document["organisation_id"]
    document_id = document["id"]

    print("Organisation ID:", organisation_id)
    print("Document ID:", document_id)

    print("\n2. Indexing document into ChromaDB...")

    result = index_document(
        pdf_path=PDF_PATH,
        organisation_id=organisation_id,
        document_id=document_id
    )

    print("Filename:", result["filename"])
    print("Total chunks:", result["total_chunks"])
    print("Indexed chunks:", result["indexed_chunks"])
    print("Collection count:", result["collection_count"])

    print("\n3. Checking organisation-specific chunks...")

    org_count = get_organisation_document_count(
        organisation_id
    )

    print("Organisation chunks:", org_count)

    print("\n4. Searching knowledge base...")

    question = (
        "What is the procedure for handling customer "
        "complaints and escalating unresolved complaints?"
    )

    passages = search_knowledge_base(
        question=question,
        organisation_id=organisation_id,
        top_k=5
    )

    print("\nRetrieved passages:", len(passages))

    print("\n5. Retrieved knowledge")
    print("=" * 65)

    print(format_retrieved_context(passages))

    print("\n6. Final database statistics")
    print("=" * 65)

    print("Total ChromaDB chunks:", get_collection_count())
    print("Organisation ID:", organisation_id)
    print("Organisation chunks:", org_count)

    print("\nRAG TEST COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    main()
