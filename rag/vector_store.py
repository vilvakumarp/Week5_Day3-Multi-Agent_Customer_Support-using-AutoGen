
import hashlib
from pathlib import Path

import chromadb

from chromadb.utils.embedding_functions import (
    SentenceTransformerEmbeddingFunction
)

from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag.document_processor import extract_pdf_text


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

RAG_DIR = BASE_DIR / "rag_db"

COLLECTION_NAME = "customer_support_knowledge"

EMBEDDING_MODEL = "all-MiniLM-L6-v2"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
BATCH_SIZE = 100


# ============================================================
# CHROMADB INITIALIZATION
# ============================================================

_client = None
_collection = None


def get_client():
    global _client

    if _client is None:
        RAG_DIR.mkdir(parents=True, exist_ok=True)

        _client = chromadb.PersistentClient(
            path=str(RAG_DIR)
        )

    return _client


def get_embedding_function():

    return SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )


def get_collection():
    global _collection

    if _collection is None:

        _collection = get_client().get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=get_embedding_function(),
            metadata={
                "description": "Organisation-specific customer support knowledge"
            }
        )

    return _collection


# ============================================================
# DOCUMENT INDEXING
# ============================================================

def index_document(
    pdf_path,
    organisation_id,
    document_id,
    progress_callback=None
):
    """
    Extract, split, embed and store a PDF in ChromaDB.

    Stable chunk IDs ensure repeated indexing does not
    create duplicate records.
    """

    pdf_path = Path(pdf_path)

    def report(percent, description):
        if progress_callback:
            progress_callback(percent, description)

    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    if not organisation_id or not document_id:
        raise ValueError(
            "Valid organisation_id and document_id are required."
        )

    # --------------------------------------------------------
    # 1. Calculate file hash
    # --------------------------------------------------------

    file_bytes = pdf_path.read_bytes()

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    report(10, "Reading PDF")

    # --------------------------------------------------------
    # 2. Extract PDF text
    # --------------------------------------------------------

    extracted = extract_pdf_text(pdf_path)
    report(30, "Extracting PDF pages")

    # --------------------------------------------------------
    # 3. Create page-aware documents
    # --------------------------------------------------------

    texts = [
        page["content"]
        for page in extracted["pages"]
    ]

    metadatas = [
        {
            "filename": pdf_path.name,
            "page": int(page["page"]),
            "organisation_id": int(organisation_id),
            "document_id": int(document_id),
            "file_hash": file_hash
        }
        for page in extracted["pages"]
    ]

    # --------------------------------------------------------
    # 4. Split documents into chunks
    # --------------------------------------------------------

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP
    )

    chunks = splitter.create_documents(
        texts=texts,
        metadatas=metadatas
    )

    if not chunks:
        raise ValueError("No text chunks were generated.")
    report(50, f"Prepared {len(chunks)} knowledge chunks")

    # --------------------------------------------------------
    # 5. Generate stable chunk IDs
    # --------------------------------------------------------

    collection = get_collection()

    total_chunks = len(chunks)

    for batch_start in range(0, total_chunks, BATCH_SIZE):

        batch = chunks[
            batch_start:batch_start + BATCH_SIZE
        ]

        ids = [
            hashlib.sha256(
                f"{file_hash}_{batch_start + i}".encode("utf-8")
            ).hexdigest()
            for i in range(len(batch))
        ]

        documents = [
            chunk.page_content
            for chunk in batch
        ]

        metadata_list = [
            chunk.metadata
            for chunk in batch
        ]

        # Upsert makes repeated indexing idempotent.
        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadata_list
        )
        report(50 + round(45 * min(batch_start + len(batch), total_chunks) / total_chunks),
               "Embedding and saving knowledge")

    report(100, "Knowledge base update complete")

    return {
        "filename": pdf_path.name,
        "file_hash": file_hash,
        "organisation_id": organisation_id,
        "document_id": document_id,
        "total_chunks": total_chunks,
        "indexed_chunks": total_chunks,
        "collection_count": collection.count()
    }


# ============================================================
# COLLECTION INFORMATION
# ============================================================

def get_collection_count():
    return get_collection().count()


def get_organisation_document_count(organisation_id):

    collection = get_collection()

    results = collection.get(
        where={
            "organisation_id": int(organisation_id)
        },
        include=["metadatas"]
    )

    return len(results["ids"])


def delete_document_knowledge(document_id):
    """Remove one document's chunks from ChromaDB; uploaded files remain intact."""
    collection = get_collection()
    existing = collection.get(where={"document_id": int(document_id)}, include=[])
    ids = existing.get("ids", [])
    if ids:
        collection.delete(ids=ids)
    return len(ids)
