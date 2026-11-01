
import pytest

from agents.response_validation_agent import has_full_source_content


def make_source(url, status="success", content=None):
    return {
        "source_url": url,
        "retrieval_status": status,
        "source_content": content or ("Verified source content. " * 15)
    }


def test_accept_official_rbi_source():
    findings = [
        make_source("https://www.rbi.org.in/example")
    ]

    assert has_full_source_content(
        findings,
        require_official_rbi=True
    ) is True


def test_reject_non_rbi_source_for_rbi_question():
    findings = [
        make_source("https://www.example.com/policy")
    ]

    assert has_full_source_content(
        findings,
        require_official_rbi=True
    ) is False


def test_accept_non_rbi_https_source():
    findings = [
        make_source("https://www.example.com/policy")
    ]

    assert has_full_source_content(
        findings,
        require_official_rbi=False
    ) is True


def test_reject_http_source():
    findings = [
        make_source("http://www.rbi.org.in/example")
    ]

    assert has_full_source_content(
        findings,
        require_official_rbi=True
    ) is False


def test_reject_failed_retrieval():
    findings = [
        make_source(
            "https://www.rbi.org.in/example",
            status="error"
        )
    ]

    assert has_full_source_content(
        findings,
        require_official_rbi=True
    ) is False


def test_reject_insufficient_content():
    findings = [
        make_source(
            "https://www.rbi.org.in/example",
            content="Too short"
        )
    ]

    assert has_full_source_content(
        findings,
        require_official_rbi=True
    ) is False


def test_reject_empty_findings():
    assert has_full_source_content(
        [],
        require_official_rbi=True
    ) is False

