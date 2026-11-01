
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader


def extract_pdf_text(pdf_path):
    """
    Extract text from a PDF using LangChain PyPDFLoader.
    Returns extracted text and page information.
    """

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    loader = PyPDFLoader(str(pdf_path))
    documents = loader.load()

    if not documents:
        raise ValueError("No text could be extracted from the PDF.")

    pages = []

    for index, document in enumerate(documents):

        page_text = document.page_content.strip()

        if page_text:
            pages.append({
                "page": index + 1,
                "content": page_text
            })

    if not pages:
        raise ValueError(
            "The PDF contains no extractable text. "
            "Scanned documents may require OCR."
        )

    full_text = "\n\n".join(
        f"Page {page['page']}:\n{page['content']}"
        for page in pages
    )

    return {
        "filename": pdf_path.name,
        "total_pages": len(documents),
        "extracted_pages": len(pages),
        "pages": pages,
        "full_text": full_text
    }


def get_document_sample(full_text, max_chars=14000):
    """
    Prepare representative text for document intelligence.
    """

    if len(full_text) <= max_chars:
        return full_text

    # Sample from the beginning, middle and end.
    section_size = max_chars // 3

    beginning = full_text[:section_size]

    middle_start = max(
        0,
        (len(full_text) // 2) - (section_size // 2)
    )

    middle = full_text[
        middle_start:middle_start + section_size
    ]

    ending = full_text[-section_size:]

    return (
        "DOCUMENT BEGINNING:\n"
        + beginning
        + "\n\nDOCUMENT MIDDLE:\n"
        + middle
        + "\n\nDOCUMENT END:\n"
        + ending
    )
