
import pytest
from io import BytesIO
from reportlab.pdfgen import canvas

from tools.source_retriever import (
    is_allowed_domain,
    is_probable_challenge_page,
    extract_webpage_content,
    extract_pdf_content,
)


def test_allowed_domain():
    assert is_allowed_domain("www.rbi.org.in", ["rbi.org.in"])


def test_reject_unapproved_domain():
    assert not is_allowed_domain("www.google.com", ["rbi.org.in"])


def test_reject_lookalike_domain():
    assert not is_allowed_domain("fake-rbi.org.in", ["rbi.org.in"])


def test_detect_captcha_page():
    title = "Security Check"
    text = (
        "This question is for testing whether you are a "
        "human visitor and to prevent automated spam submissions."
    )

    assert is_probable_challenge_page(title, text)


def test_normal_page_not_detected_as_captcha():
    title = "RBI Notifications"
    text = "Reserve Bank of India notifications and circulars."

    assert not is_probable_challenge_page(title, text)


def test_extract_html_content():
    html = """
    <html>
        <head><title>RBI Guidelines</title></head>
        <body>
            <h1>Customer Grievance Redressal</h1>
            <p>Customers can submit complaints through the bank.</p>
        </body>
    </html>
    """

    result = extract_webpage_content(html)

    assert result["content_type"] == "html"
    assert result["title"] == "RBI Guidelines"
    assert "Customer Grievance Redressal" in result["full_text"]


def test_extract_pdf_content():
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(100, 750, "Customer Grievance Redressal")
    pdf.save()

    result = extract_pdf_content(buffer.getvalue())

    assert result["content_type"] == "pdf"
    assert "Customer Grievance Redressal" in result["full_text"]

from tools import source_retriever


class MockResponse:
    def __init__(self, content, content_type, url):
        self.content = content
        self.headers = {"Content-Type": content_type}
        self.url = url
        self.is_redirect = False
        self.is_permanent_redirect = False
        self.closed = False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=65536):
        yield self.content

    def close(self):
        self.closed = True



def test_retrieve_valid_pdf(monkeypatch):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(
        100, 750,
        "This is a valid PDF containing customer grievance information."
    )
    pdf.save()

    url = "https://www.rbi.org.in/sample.pdf"

    mock_response = MockResponse(
        buffer.getvalue(),
        "application/pdf",
        url
    )

    monkeypatch.setattr(
        source_retriever.requests,
        "get",
        lambda *args, **kwargs: mock_response
    )

    result = source_retriever.retrieve_source(
        url,
        allowed_domains=["rbi.org.in"]
    )

    assert result["status"] == "success"
    assert result["content_type"] == "pdf"
    assert "customer grievance" in result["full_text"].lower()


def test_retrieve_captcha_page(monkeypatch):
    url = "https://www.rbi.org.in/security-check"

    html = """
    <html>
        <head><title>Security Check</title></head>
        <body>
            This question is for testing whether you are a
            human visitor and to prevent automated spam submissions.
        </body>
    </html>
    """

    mock_response = MockResponse(
        html.encode("utf-8"),
        "text/html",
        url
    )

    monkeypatch.setattr(
        source_retriever.requests,
        "get",
        lambda *args, **kwargs: mock_response
    )

    result = source_retriever.retrieve_source(
        url,
        allowed_domains=["rbi.org.in"]
    )

    assert result["status"] == "blocked"
    assert "CAPTCHA" in result["error"]


def test_retrieve_empty_html(monkeypatch):
    url = "https://www.rbi.org.in/empty-page"

    html = """
    <html>
        <head><title>Empty Page</title></head>
        <body></body>
    </html>
    """

    mock_response = MockResponse(
        html.encode("utf-8"),
        "text/html",
        url
    )

    monkeypatch.setattr(
        source_retriever.requests,
        "get",
        lambda *args, **kwargs: mock_response
    )

    result = source_retriever.retrieve_source(
        url,
        allowed_domains=["rbi.org.in"]
    )

    assert result["status"] == "error"
    assert "insufficient extractable text" in result["error"].lower()
