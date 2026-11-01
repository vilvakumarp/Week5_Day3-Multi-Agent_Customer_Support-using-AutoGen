
import asyncio
import hashlib
from pathlib import Path

from rag.document_processor import (
    extract_pdf_text,
    get_document_sample
)

from agents.document_intelligence import analyse_document

from database.db_manager import (
    init_db,
    get_or_create_organisation,
    register_document
)


async def main():

    pdf_path = Path(
        "data/uploaded_pdfs/standard-operating-procedure-for-handling-customer.pdf"
    )

    print("\n1. Initialising database...")
    init_db()

    print("\n2. Extracting PDF content...")
    document = extract_pdf_text(pdf_path)

    sample = get_document_sample(document["full_text"])

    print("Filename:", document["filename"])
    print("Pages:", document["total_pages"])

    print("\n3. Analysing document...")
    result = await analyse_document(sample)

    print("\n4. Saving organisation information...")

    organisation_name = result["organisation_name"]

    if not organisation_name or organisation_name.upper() == "UNKNOWN":
        raise ValueError(
            "Organisation could not be identified. "
            "Document registration requires manual review."
        )

    organisation_id = get_or_create_organisation(
        name=organisation_name,
        domain=result["industry"],
        official_website=result["official_website"] or None,
        metadata=result
    )

    print("Organisation ID:", organisation_id)

    print("\n5. Registering document...")

    file_hash = hashlib.sha256(
        pdf_path.read_bytes()
    ).hexdigest()

    document_id = register_document(
        filename=document["filename"],
        file_hash=file_hash,
        file_path=pdf_path,
        organisation_id=organisation_id,
        metadata={
            "document_category": result["document_category"],
            "topics": result["topics"],
            "confidence": result["confidence"]
        }
    )

    print("Document ID:", document_id)

    print("\n" + "=" * 55)
    print("DOCUMENT REGISTRATION COMPLETED")
    print("=" * 55)

    print("Organisation:", organisation_name)
    print("Industry:", result["industry"])
    print("Document:", document["filename"])
    print("Topics:", result["topics"])


if __name__ == "__main__":
    asyncio.run(main())
