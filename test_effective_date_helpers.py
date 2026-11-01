from datetime import date

from agents.response_validation_agent import (
    extract_effective_dates,
    effective_date_contradictions,
    classify_effective_date,
    is_future_date,
    parse_date,
    synchronize_validation_issues,
    passage_matches,
    normalise_evidence_url,
    verify_claim_evidence,
)


TEST_TODAY = date(2026, 11, 1)


def test_date_comparison_supports_common_formats():
    assert is_future_date("1 December 2026", TEST_TODAY)
    assert is_future_date("2027-01-01", TEST_TODAY)
    assert not is_future_date("1 July 2026", TEST_TODAY)
    assert not is_future_date("November 1, 2026", TEST_TODAY)
    assert not is_future_date("invalid", TEST_TODAY)
    assert classify_effective_date("1 July 2026", TEST_TODAY) == "past"
    assert classify_effective_date("1 July 2026", date(2026, 6, 1)) == "future"
    assert classify_effective_date("1 November 2026", TEST_TODAY) == "today"
    assert classify_effective_date("1 December 2026", TEST_TODAY) == "future"


def test_passage_matching_allows_formatting_but_not_unrelated_evidence():
    source = "RB-IOS, 2026 comes into force with effect from July 1, 2026."
    assert passage_matches(source, "RB-IOS, 2026 comes into force with effect from\nJuly 1, 2026.")
    assert not passage_matches(source, "The scheme applies to all banks.")


def test_url_normalisation_preserves_path_and_query_identity():
    assert normalise_evidence_url("HTTPS://RBI.ORG.IN:443/a/?x=1#section") == "https://rbi.org.in/a?x=1"
    assert normalise_evidence_url("https://rbi.org.in/a?x=1") != normalise_evidence_url("https://rbi.org.in/a?x=2")
    assert normalise_evidence_url("https://rbi.org.in/a") != normalise_evidence_url("https://rbi.org.in/b")


def test_deterministic_web_and_rag_evidence_verification():
    claim = {
        "claim": "The scheme starts on 1 July 2026.",
        "source_title": "RBI scheme",
        "source_url": "HTTPS://RBI.ORG.IN:443/scheme/#top",
        "supporting_passage": "The scheme starts on 1 July 2026.",
    }
    web = [{
        "retrieval_status": "success",
        "source_title": "RBI scheme",
        "source_url": "https://rbi.org.in/scheme",
        "source_content": "The scheme starts on 1 July 2026.",
    }]
    reference = verify_claim_evidence(claim, web, [], 2)
    assert reference and reference["source_type"] == "web"
    assert verify_claim_evidence(claim, [{**web[0], "retrieval_status": "failed"}], [], 2) is None
    assert verify_claim_evidence(claim, [{**web[0], "source_url": "https://rbi.org.in/other"}], [], 2) is None
    assert verify_claim_evidence({**claim, "supporting_passage": "Unrelated passage."}, web, [], 2) is None

    rag_claim = {"claim": "Complaints take 30 days.", "supporting_passage": "Complaints take 30 days."}
    rag = [{"organisation_id": 2, "filename": "sop.pdf", "page": 3, "content": "Complaints take 30 days."}]
    rag_reference = verify_claim_evidence(rag_claim, [], rag, 2)
    assert rag_reference and rag_reference["source_type"] == "rag"
    assert verify_claim_evidence(rag_claim, [], [{**rag[0], "organisation_id": 3}], 2) is None


def test_effective_date_extraction_is_conservative_and_traceable():
    findings = [{
        "retrieval_status": "success",
        "source_title": "Official direction",
        "source_url": "https://example.gov/direction",
        "source_content": (
            "Published 15 June 2026. Notification date: 20 June 2026. "
            "The direction becomes effective from 1 July 2026. "
            "Compliance deadline is 1 December 2026. "
            "Transition period ends 31 December 2026."
        ),
    }, {
        "retrieval_status": "failed",
        "source_title": "Unavailable",
        "source_url": "https://example.gov/unavailable",
        "source_content": "Effective from 1 January 2027.",
    }]

    dates = extract_effective_dates(findings)

    assert len(dates) == 1
    assert dates[0]["effective_date"] == "2026-07-01"
    assert dates[0]["source_title"] == "Official direction"
    assert dates[0]["source_url"] == "https://example.gov/direction"
    assert parse_date("July 1, 2026") == date(2026, 7, 1)


def test_date_language_contradictions_are_flagged_without_approval():
    past = [{"date": "1 July 2026", "effective_date": "2026-07-01"}]
    future = [{"date": "1 December 2026", "effective_date": "2026-12-01"}]
    assert effective_date_contradictions(
        "The regulation is upcoming from 1 July 2026.", past, TEST_TODAY
    )
    assert effective_date_contradictions(
        "The regulation is currently effective from 1 December 2026.", future, TEST_TODAY
    )


def test_date_language_phrases_are_classified_without_in_force_false_positive():
    future = [{"date": "1 December 2026", "effective_date": "2026-12-01"}]
    past = [{"date": "1 July 2026", "effective_date": "2026-07-01"}]
    assert not effective_date_contradictions(
        "The regulation will come into force on 1 December 2026.", future, TEST_TODAY
    )
    assert not effective_date_contradictions(
        "The regulation will become effective on 1 December 2026.", future, TEST_TODAY
    )
    assert effective_date_contradictions(
        "The regulation is currently in force from 1 December 2026.", future, TEST_TODAY
    )
    assert effective_date_contradictions(
        "The regulation is already effective from 1 December 2026.", future, TEST_TODAY
    )
    assert effective_date_contradictions(
        "The regulation became effective on 1 December 2026.", future, TEST_TODAY
    )
    assert not effective_date_contradictions(
        "The regulation is not yet effective as of 1 December 2026.", future, TEST_TODAY
    )


def test_multiple_regulations_require_date_statement_association():
    findings = [
        {"date": "1 July 2026", "effective_date": "2026-07-01"},
        {"date": "1 December 2026", "effective_date": "2026-12-01"},
    ]
    response = (
        "Regulation A is upcoming. Regulation B will come into force on 1 December 2026."
    )
    assert effective_date_contradictions(response, findings, TEST_TODAY) == []


def test_negative_current_status_phrases_are_not_positive_status():
    future = [{"date": "1 December 2026", "effective_date": "2026-12-01"}]
    assert not effective_date_contradictions(
        "The regulation is not currently effective on 1 December 2026.", future, TEST_TODAY
    )
    assert not effective_date_contradictions(
        "The regulation is not yet in force on 1 December 2026.", future, TEST_TODAY
    )
    assert not effective_date_contradictions(
        "The regulation is not already effective on 1 December 2026.", future, TEST_TODAY
    )


def test_two_dates_in_one_sentence_are_not_automatically_associated():
    findings = [
        {"date": "1 July 2026", "effective_date": "2026-07-01"},
        {"date": "1 December 2026", "effective_date": "2026-12-01"},
    ]
    response = (
        "Regulation A is currently effective from 1 July 2026 and Regulation B "
        "is currently effective from 1 December 2026."
    )
    assert effective_date_contradictions(response, findings, TEST_TODAY) == []


def test_duplicate_sources_confirming_one_date_count_as_one_date():
    findings = [
        {"date": "1 December 2026", "effective_date": "2026-12-01", "source_url": "https://a.example"},
        {"date": "December 1, 2026", "effective_date": "2026-12-01", "source_url": "https://b.example"},
    ]
    response = "The regulation is currently effective from 1 December 2026."
    assert effective_date_contradictions(response, findings, TEST_TODAY)


def test_issue_sync_removes_only_resolved_claim_issue():
    issues, claims = synchronize_validation_issues(
        ["unsupported deadline claim", "Applicability is not established"],
        ["unsupported deadline claim"],
        "The answer omits the deadline."
    )
    assert issues == ["Applicability is not established"]
    assert claims == []
