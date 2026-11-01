
import requests
from io import BytesIO
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from pypdf import PdfReader

import ipaddress
from urllib.parse import urljoin


def extract_pdf_content(content):
    """
    Extract text from a downloaded PDF.
    """

    reader = PdfReader(BytesIO(content))

    pages = []

    for page_number, page in enumerate(reader.pages, start=1):

        text = page.extract_text() or ""

        if text.strip():

            pages.append({
                "page": page_number,
                "text": text.strip()
            })

    return {
        "content_type": "pdf",
        "total_pages": len(reader.pages),
        "pages": pages,
        "full_text": "\n\n".join(
            page["text"] for page in pages
        )
    }


def extract_webpage_content(content):
    """
    Extract readable text from an HTML webpage.
    """

    soup = BeautifulSoup(content, "html.parser")

    # Remove non-content elements.
    for element in soup([
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "noscript"
    ]):
        element.decompose()

    title = (
        soup.title.get_text(strip=True)
        if soup.title else ""
    )

    text = soup.get_text(separator="\n")

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    full_text = "\n".join(lines)

    return {
        "content_type": "html",
        "title": title,
        "full_text": full_text
    }


def is_probable_challenge_page(title, full_text):
    """
    Detect CAPTCHA and anti-bot challenge pages.
    Uses specific phrases to reduce false positives.
    """

    content = f"{title}\n{full_text}".lower()

    challenge_phrases = [
        "this question is for testing whether you are a human visitor",
        "to prevent automated spam submissions",
        "verify you are human",
        "please verify that you are human",
        "checking your browser",
        "complete the security check",
        "captcha challenge",
        "unusual traffic detected",
        "automated requests are not allowed",
    ]

    return any(
        phrase in content
        for phrase in challenge_phrases
    )


def is_allowed_domain(hostname, allowed_domains):
    """
    Check whether a hostname matches an explicitly allowed domain.
    Subdomains are allowed, but lookalike domains are rejected.
    """

    if not hostname or not allowed_domains:
        return False

    hostname = hostname.lower().rstrip(".")

    # Reject IP addresses and local hostnames.
    try:
        ipaddress.ip_address(hostname)
        return False
    except ValueError:
        pass

    if hostname in ("localhost",):
        return False

    for domain in allowed_domains:
        domain = domain.lower().strip().rstrip(".")

        if hostname == domain or hostname.endswith("." + domain):
            return True

    return False


def validate_source_url(url, allowed_domains):
    """
    Validate HTTPS URL and its hostname before making a request.
    """

    parsed = urlparse(url)

    if parsed.scheme.lower() != "https":
        raise ValueError("Only HTTPS source URLs are permitted.")

    if not parsed.hostname:
        raise ValueError("Invalid source URL: hostname is missing.")

    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not permitted.")

    if parsed.port not in (None, 443):
        raise ValueError("Non-standard URL ports are not permitted.")

    if not is_allowed_domain(parsed.hostname, allowed_domains):
        raise ValueError(
            f"Domain not allowed: {parsed.hostname}"
        )

    return parsed


def retrieve_source(
    url,
    allowed_domains,
    timeout=30,
    max_bytes=20_000_000,
    max_redirects=5
):
    """
    Download and extract a PDF or HTML webpage.

    Only explicitly allowlisted HTTPS domains are permitted.
    Every redirect destination is validated before it is requested.

    Returns a dictionary with status='success' or status='error'.
    """

    result = {
        "status": "error",
        "source_url": url,
        "final_url": None,
        "content_type": None,
        "title": "",
        "total_pages": None,
        "full_text": "",
        "pages": [],
        "error": None
    }

    response = None

    try:
        if not url:
            raise ValueError("Source URL is empty.")

        current_url = url

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/pdf,text/html,*/*",
            "Accept-Language": "en-US,en;q=0.9"
        }

        # Validate every URL before requesting it.
        for redirect_count in range(max_redirects + 1):

            validate_source_url(current_url, allowed_domains)

            response = requests.get(
                current_url,
                headers=headers,
                timeout=timeout,
                stream=True,
                allow_redirects=False
            )

            # Handle redirects manually.
            if response.is_redirect or response.is_permanent_redirect:

                location = response.headers.get("Location")
                response.close()
                response = None

                if not location:
                    raise ValueError(
                        "Redirect response did not contain a destination."
                    )

                if redirect_count >= max_redirects:
                    raise ValueError("Maximum redirect limit exceeded.")

                current_url = urljoin(current_url, location)

                # The next iteration validates the new destination
                # before making another HTTP request.
                continue

            response.raise_for_status()
            break

        else:
            raise ValueError("Unable to resolve source URL.")

        content_length = response.headers.get("Content-Length")

        if content_length and int(content_length) > max_bytes:
            raise ValueError(
                "Source file exceeds the maximum allowed size."
            )

        content = bytearray()

        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                content.extend(chunk)

                if len(content) > max_bytes:
                    raise ValueError(
                        "Downloaded content exceeds the maximum allowed size."
                    )

        content = bytes(content)

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        final_url = response.url
        final_path = urlparse(final_url).path.lower()

        is_pdf = (
            "application/pdf" in content_type
            or final_path.endswith(".pdf")
            or content.startswith(b"%PDF-")
        )

        if is_pdf:
            extracted = extract_pdf_content(content)

        elif (
            "text/html" in content_type
            or "application/xhtml+xml" in content_type
        ):
            extracted = extract_webpage_content(content)

        else:
            raise ValueError(
                f"Unsupported content type: {content_type}"
            )

        
        extracted_text = extracted.get("full_text", "").strip()
        extracted_title = extracted.get("title", "")

        # Reject CAPTCHA and anti-bot challenge pages.
        if extracted["content_type"] == "html" and is_probable_challenge_page(
            extracted_title,
            extracted_text
        ):
            result.update({
                "status": "blocked",
                "final_url": final_url,
                "content_type": extracted["content_type"],
                "title": extracted_title,
                "error": (
                    "Source returned a CAPTCHA or anti-bot challenge "
                    "instead of usable document content."
                )
            })

            return result

        # Reject pages or PDFs with no extractable text.
        if len(extracted_text) < 40:
            result.update({
                "status": "error",
                "final_url": final_url,
                "content_type": extracted["content_type"],
                "title": extracted_title,
                "error": (
                    "Source contains insufficient extractable text "
                    "to be used as evidence."
                )
            })

            return result


        result.update({
            "status": "success",
            "final_url": final_url,
            "content_type": extracted["content_type"],
            "title": extracted.get("title", ""),
            "total_pages": extracted.get("total_pages"),
            "full_text": extracted["full_text"],
            "pages": extracted.get("pages", []),
            "error": None
        })

    except requests.exceptions.HTTPError as e:
        status_code = (
            e.response.status_code if e.response is not None else None
        )
        result["error"] = f"HTTP error {status_code}: {e}"

    except requests.exceptions.Timeout:
        result["error"] = "The source website took too long to respond."

    except requests.exceptions.ConnectionError:
        result["error"] = "Could not connect to the source website."

    except requests.exceptions.RequestException as e:
        result["error"] = f"Download error: {e}"

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    finally:
        if response is not None:
            response.close()

    return result

