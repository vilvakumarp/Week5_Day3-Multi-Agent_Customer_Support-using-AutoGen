
from rag.vector_store import get_collection


def search_knowledge_base(
    question,
    organisation_id,
    top_k=5,
    document_id=None
):
    """
    Search the persistent RAG database.

    Results are restricted to the specified organisation.
    An optional document_id can narrow the search further.
    """

    if not question or not question.strip():
        raise ValueError("Search question cannot be empty.")

    if organisation_id is None:
        raise ValueError(
            "Organisation ID is required for scoped retrieval."
        )

    collection = get_collection()

    if collection.count() == 0:
        return []

    # --------------------------------------------------------
    # Organisation-specific metadata filter
    # --------------------------------------------------------

    where_filter = {
        "organisation_id": int(organisation_id)
    }

    if document_id is not None:

        where_filter = {
            "$and": [
                {
                    "organisation_id": int(organisation_id)
                },
                {
                    "document_id": int(document_id)
                }
            ]
        }

    # --------------------------------------------------------
    # Retrieve relevant chunks
    # --------------------------------------------------------

    results = collection.query(
        query_texts=[question],
        n_results=top_k,
        where=where_filter, # type: ignore
        include=[
            "documents",
            "metadatas",
            "distances"
        ]
    )

    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]

    retrieved_passages = []

    for text, metadata, distance in zip(
        documents,
        metadatas,
        distances
    ):

        retrieved_passages.append({
            "content": text,
            "filename": metadata.get("filename"),
            "page": metadata.get("page"),
            "organisation_id": metadata.get("organisation_id"),
            "document_id": metadata.get("document_id"),
            "distance": float(distance) if distance is not None else None
        })

    return retrieved_passages


def format_retrieved_context(passages):
    """
    Convert retrieved passages into readable context
    for the AutoGen RAG Agent.
    """

    if not passages:
        return (
            "No relevant information was found in the "
            "organisation-specific knowledge base."
        )

    formatted = []

    for index, passage in enumerate(passages, start=1):

        formatted.append(
            f"""
SOURCE {index}
Document: {passage['filename']}
Page: {passage['page']}

Content:
{passage['content']}
"""
        )

    return "\n\n".join(formatted)
