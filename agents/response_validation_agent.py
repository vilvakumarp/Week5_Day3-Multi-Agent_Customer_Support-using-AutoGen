
import os
import json
from datetime import date, datetime
import re
from urllib.parse import urlsplit, urlunsplit
from dotenv import load_dotenv

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient


load_dotenv()

def parse_date(date_text: str):
    """Parse supported human-readable dates, returning ``date`` or None."""
    if not isinstance(date_text, str):
        return None
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%B %d, %Y", "%B %d %Y"):
        try:
            return datetime.strptime(date_text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _normalized_date_value(date_text: str) -> str:
    parsed = parse_date(date_text)
    return parsed.isoformat() if parsed is not None else date_text.lower()


def normalise_evidence_text(value: str) -> str:
    """Normalise harmless formatting differences while preserving wording."""
    return re.sub(r"\s+", " ", value or "").strip().casefold()


def passage_matches(source_content: str, supporting_passage: str) -> bool:
    if not isinstance(source_content, str) or not isinstance(supporting_passage, str):
        return False
    return normalise_evidence_text(supporting_passage) in normalise_evidence_text(source_content)


def normalise_evidence_url(value: str) -> str:
    """Normalize URL presentation without changing path or query identity."""
    if not isinstance(value, str) or not value.strip():
        return ""
    parsed = urlsplit(value.strip())
    if not parsed.scheme or not parsed.hostname:
        return ""
    hostname = parsed.hostname.casefold()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    try:
        port = parsed.port
    except ValueError:
        return ""
    if port and not ((parsed.scheme.casefold() == "https" and port == 443) or
                     (parsed.scheme.casefold() == "http" and port == 80)):
        hostname = f"{hostname}:{port}"
    netloc = hostname
    if parsed.username or parsed.password:
        return ""
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.casefold(), netloc, path, parsed.query, ""))


def verify_claim_evidence(claim_item, web_findings, rag_passages, organisation_id):
    """Deterministically verify one supported claim and return its reference."""
    if isinstance(claim_item, dict):
        claim = claim_item.get("claim", "")
        supporting_passage = claim_item.get("supporting_passage", "")
        source_url = claim_item.get("source_url", "")
        source_title = claim_item.get("source_title", "")
    elif isinstance(claim_item, str):
        claim, supporting_passage, source_url, source_title = claim_item, claim_item, "", ""
    else:
        return None
    if not isinstance(claim, str) or not claim.strip() or not isinstance(supporting_passage, str) or not supporting_passage.strip():
        return None
    if source_url:
        wanted_url = normalise_evidence_url(source_url)
        if not wanted_url:
            return None
        for finding in web_findings or []:
            if not isinstance(finding, dict) or finding.get("retrieval_status") != "success":
                continue
            if normalise_evidence_url(finding.get("source_url", "")) != wanted_url:
                continue
            if passage_matches(finding.get("source_content", ""), supporting_passage):
                return {
                    "source_type": "web", "claim": claim,
                    "source_name": finding.get("source_title") or source_title,
                    "source_url": finding.get("source_url"), "page": None,
                    "supporting_passage": supporting_passage,
                }
    for passage in rag_passages or []:
        if not isinstance(passage, dict) or organisation_id is None:
            continue
        if passage.get("organisation_id") is None or str(passage.get("organisation_id")) != str(organisation_id):
            continue
        if passage_matches(passage.get("content", ""), supporting_passage):
            return {
                "source_type": "rag", "claim": claim,
                "source_name": passage.get("filename"), "source_url": None,
                "page": passage.get("page"), "document_id": passage.get("document_id"),
                "supporting_passage": supporting_passage,
            }
    return None


def classify_effective_date(effective_date, today=None):
    """Classify an effective date relative to one injectable current date."""
    if isinstance(effective_date, str):
        effective_date = parse_date(effective_date)
    if effective_date is None:
        return None
    reference_date = today or date.today()
    if effective_date < reference_date:
        return "past"
    if effective_date > reference_date:
        return "future"
    return "today"


def is_future_date(date_text: str, today=None) -> bool:
    """
    Returns True only when the supplied date is after today.
    Supports ISO and common long-date formats. ``today`` is injectable for tests.
    """
    try:
        effective_date = parse_date(date_text)
        return bool(effective_date and effective_date > (today or date.today()))

    except (ValueError, TypeError):
        return False


def effective_date_contradictions(response, effective_dates, today=None):
    """Return contradictions only when date and language share a statement."""
    if not isinstance(response, str):
        return []
    today = today or date.today()
    contradictions = []
    future_words = re.compile(
        r"\b(upcoming|will become effective|will come into force|not yet effective|future)\b", re.I
    )
    current_words = re.compile(
        r"\b(currently effective|already effective|effective now|currently in force|became effective)\b", re.I
    )
    sentences = re.split(r"(?<=[.!?])\s+", response)
    for item in effective_dates or []:
        effective = item.get("effective_date") if isinstance(item, dict) else None
        if not isinstance(effective, str):
            continue
        effective_date = parse_date(effective)
        if not effective_date:
            continue
        item_date_text = item.get("date") if isinstance(item, dict) else None
        date_forms = {effective, effective_date.isoformat()}
        if isinstance(item_date_text, str):
            date_forms.add(item_date_text)
        # A contradiction is automatic only when the response statement names
        # this specific date. Otherwise multiple regulations could be conflated.
        matching_sentences = [
            sentence for sentence in sentences
            if any(form.lower() in sentence.lower() for form in date_forms)
        ]
        for sentence in matching_sentences:
            lowered_sentence = sentence.lower()
            if re.search(
                r"\bnot\s+(?:currently effective|yet in force|already effective|currently in force|effective now)",
                lowered_sentence,
            ):
                continue
            # If a sentence contains multiple extracted dates, Python cannot
            # safely associate either date with a particular regulation.
            distinct_dates_in_sentence = {
                _normalized_date_value(form)
                for other in (effective_dates or [])
                if isinstance(other, dict)
                for form in (other.get("effective_date"), other.get("date"))
                if isinstance(form, str) and form.lower() in lowered_sentence
            }
            if len(distinct_dates_in_sentence) > 1:
                continue
            classification = classify_effective_date(effective_date, today)
            if classification == "future" and current_words.search(sentence):
                contradictions.append(
                    f"The response describes the regulation as effective now, but the verified effective date is {effective_date.isoformat()}."
                )
            elif classification in {"past", "today"} and future_words.search(sentence):
                contradictions.append(
                    f"The response describes the regulation as upcoming, but the verified effective date was {effective_date.isoformat()}."
                )
    return contradictions


def synchronize_validation_issues(issues, unsupported_claims, corrected_response):
    """Drop only resolved unsupported-claim issues; retain unrelated issues."""
    issues = issues if isinstance(issues, list) else []
    claims = unsupported_claims if isinstance(unsupported_claims, list) else []
    response = str(corrected_response or "").lower()
    resolved = [c for c in claims if isinstance(c, str) and c.strip() and c.lower() not in response]
    remaining_claims = [c for c in claims if c not in resolved]
    remaining_issues = [
        issue for issue in issues
        if not any(
            isinstance(issue, str) and isinstance(claim, str)
            and (issue.strip() == claim.strip() or claim.lower() in issue.lower())
            for claim in resolved
        )
    ]
    return remaining_issues, remaining_claims

async def validate_response(
    question,
    organisation,
    proposed_response,
    rag_passages=None,
    web_findings=None,
    conversation_history=None
):
    """
    Validate a proposed customer response against available evidence.

    Returns a structured validation result.
    """

    api_key = os.getenv("OPENAI_API_KEY")
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing in .env")

    rag_passages = rag_passages or []
    web_findings = web_findings or []

    model_client = OpenAIChatCompletionClient(
        model=model_name,
        api_key=api_key
    )

    system_message = """
You are a Response Validation Agent in a customer support system.

Your job is to review a proposed customer response before it
is delivered to the customer.

You must validate the response against the evidence supplied
to you. Do not answer from your general knowledge.

VALIDATION RULES:

1. FACTUAL SUPPORT
- Every important factual claim must be supported by the supplied evidence.
- Do not approve invented or unsupported claims.
- Distinguish facts from assumptions.

2. ORGANISATION ACCURACY
- Ensure the response refers to the correct organisation.
- Do not mix policies or information from different organisations.

3. NUMERICAL ACCURACY
- Check dates, turnaround times, percentages and amounts carefully.
- Preserve the exact meaning and conditions in the source.
- Do not generalise a special-case deadline.

4. SOURCE ACCURACY
- Web-derived claims must have supporting source URLs.
- Do not invent URLs or source titles.
- Search snippets are preliminary evidence, not verified full policy text.
- If evidence is insufficient, clearly identify this limitation.
ADDITIONAL SOURCE VERIFICATION RULES:

- A search result snippet is not equivalent to reading
  the original source document.

- A source title containing a year does not prove
  that the document contains the latest applicable guidelines.

- Do not infer an effective date from a search result
  unless the supplied evidence explicitly states it.

- A general RBI FAQ must not automatically be treated
  as the latest regulatory direction.

- Distinguish between:
  a) RBI regulatory directions
  b) RBI Integrated Ombudsman Scheme
  c) RBI annual reports
  d) Individual bank grievance policies

- Do not combine these different document types into
  one regulatory requirement without supporting evidence.

- For questions asking for the latest or current guidelines,
  require evidence from the original official source.

- If only search-result snippets are supplied, do not
  approve detailed claims about regulatory requirements.
INSTITUTIONAL APPLICABILITY VALIDATION:

- Before approving any regulatory requirement, identify
  which category of institution the regulation applies to.

- Compare the regulation's applicability criteria with
  the supplied organisation profile.

- Check whether the regulation applies to:
  a) All scheduled commercial banks
  b) Private sector banks
  c) Public sector banks
  d) Small Finance Banks
  e) Regional Rural Banks
  f) Cooperative Banks
  g) NBFCs
  h) Payment Aggregators
  i) Other specifically defined entities

- Check any conditions, thresholds, eligibility criteria,
  business activities and effective dates mentioned in
  the original regulatory source.

- Do not apply a regulation meant exclusively for
  Small Finance Banks to a Private Sector Scheduled
  Commercial Bank.

- Do not assume that a regulation applies to an organisation
  merely because it is regulated by RBI.

- If applicability is conditional, explain the condition.

- If applicability cannot be established from the supplied
  evidence, use insufficient_evidence rather than approving
  the regulatory claim.
CONDITIONAL ELIGIBILITY RULE:

- If a regulation specifies a numerical threshold,
  eligibility condition or qualifying business activity,
  verify that the organisation meets that condition.

- Do not assume that the organisation meets a threshold
  when the required organisational data is missing.

- If the evidence explains the condition but does not
  establish whether the organisation satisfies it,
  return insufficient_evidence.

- A conditional explanation may be provided, but it must
  not be presented as a confirmed regulatory obligation.

- Use needs_revision when the correct applicability
  information is established by the evidence.

- Use insufficient_evidence when the organisation's
  eligibility cannot be determined from the available data.

REGULATORY EFFECTIVE-DATE VALIDATION:

- Identify the publication date and effective date separately.

- Do not assume that a regulation becomes effective on
  its publication or notification date.

- Compare the effective date with the date on which
  the customer is asking the question.

- If a regulation has been announced but its effective
  date is in the future, do not describe it as currently
  applicable.

- Check whether the regulation has a phased implementation
  schedule or transition period.

- Check whether the original regulation has been amended,
  superseded, repealed or withdrawn, using supplied evidence.

- Do not assume that an older regulation is still applicable
  merely because its original document is available.

- If the effective date or current status cannot be
  established from the supplied official evidence,
  use insufficient_evidence.

- Clearly distinguish between:
  a) Publication date
  b) Notification date
  c) Effective date
  d) Compliance deadline
  e) Transition period

5. COMPLETENESS
- Check whether the response addresses the customer's question.
- Identify important missing information.

6. CUSTOMER COMMUNICATION
- The response should be clear, professional and understandable.
- Avoid unsupported promises or guarantees.

7. EVIDENCE TRACEABILITY
RAG EVIDENCE TRACEABILITY:

- RAG evidence originates from the organisation's
  uploaded documents.

- For every claim supported by RAG evidence, identify:
  a) The original filename
  b) The PDF page number
  c) The exact supporting passage

- Use the filename and page number supplied
  in the retrieved RAG passage.

- Do not invent filenames or page numbers.

- Verify that the supporting passage exists
  in the supplied RAG evidence.

- Do not cite a RAG passage belonging to
  a different organisation.

- If the supporting passage cannot be identified,
  do not create a verified evidence reference.

- Every important factual claim must be traceable
  to the supplied RAG or web research evidence.

- For every supported claim, identify:
  a) The claim being verified
  b) The source title
  c) The source URL
  d) The exact supporting passage

- Use only source titles and URLs supplied in the evidence.

- Do not invent source titles, URLs, page numbers
  or supporting passages.

- Supporting passages must accurately represent
  the original source content.

- If a claim has no identifiable supporting passage,
  classify it as unsupported.

- If multiple sources support a claim, include
  the relevant sources.

- Do not treat a source URL alone as proof
  that a claim is supported.


APPROVAL RULES:

- approved:
  All material claims are supported by the supplied evidence.

- needs_revision:
  The proposed response contains an incorrect or misleading claim,
  but the supplied evidence provides the correct information.

- insufficient_evidence:
  The proposed response makes a claim that cannot be verified
  using the supplied evidence, and no reliable replacement fact
  is available.

ADDITIONAL RULES:

- Every unsupported claim must also be listed in the issues array.
- Do not use needs_revision merely because evidence is missing.
- If a compensation amount, policy, benefit or guarantee is not
  established by the supplied evidence, use insufficient_evidence.
- Never interpret absence of evidence as proof that a policy does
  not exist.
- In insufficient_evidence cases, explain what information could
  not be verified.

CORRECTION CONSISTENCY RULES:

- When returning needs_revision, provide a corrected
  validated_response.

- Remove every unsupported claim from the corrected response.

- Do not retain an unsupported claim in the corrected response
  merely because it appeared in the original response.

- The issues array must describe problems that remain relevant
  to the corrected response or explain why correction was necessary.

- If all unsupported claims have been removed and every remaining
  material claim is supported by the supplied evidence,
  return approved.

- Do not return needs_revision solely because the original
  proposed response contained a claim that has now been corrected.

- If the supplied evidence cannot establish a reliable correction,
  return insufficient_evidence.

Return valid JSON only:

{
    "validation_status": "approved | needs_revision | insufficient_evidence",
    "confidence": "high | medium | low",
    "issues": [],
    "supported_claims": [],
    "unsupported_claims": [],
    "corrections_required": false,
    "validated_response": "Final corrected response, or empty if evidence is insufficient",
    "validation_summary": "Short explanation",
    "evidence_references": [
        {
            "claim": "The claim being verified",
            "source_title": "Original source title",
            "source_url": "Original source URL",
            "supporting_passage": "Exact supporting passage"
        }
    ]
}

IMPORTANT:
- Never approve a response merely because it sounds plausible.
- Do not add facts that are absent from the supplied evidence.
- If a correction is required, correct only what the evidence supports.
- If evidence is insufficient, do not fabricate a replacement answer.
- Return JSON only, without Markdown fences.

"""

    agent = AssistantAgent(
        name="response_validation_agent",
        model_client=model_client,
        system_message=system_message
    )

    current_date_value = date.today()
    current_date = current_date_value.isoformat()
    effective_date_findings = extract_effective_dates(web_findings)

    task = f"""
CURRENT DATE:
{current_date}

DATE VALIDATION INSTRUCTIONS:
- Use the current date above when evaluating effective dates.
- Distinguish publication dates from effective dates.
- If the effective date is before the current date,
  do not describe the regulation as upcoming.
- If the effective date is after the current date,
  do not describe it as currently effective.
- Check transition periods and phased implementation dates.
- Do not assume a regulation is applicable merely because
  it has been published.

CUSTOMER QUESTION:
{question}

PREVIOUS CONVERSATION CONTEXT:
{conversation_history or "No previous messages; treat this as a new conversation."}

ORGANISATION:
{json.dumps(organisation, ensure_ascii=False, default=str)}

RAG EVIDENCE:
{json.dumps(rag_passages, ensure_ascii=False, default=str)}

WEB RESEARCH FINDINGS:
{json.dumps(web_findings, ensure_ascii=False, default=str)}

EXPLICIT EFFECTIVE DATES EXTRACTED FROM SUCCESSFULLY RETRIEVED SOURCES:
{json.dumps(effective_date_findings, ensure_ascii=False, default=str)}

PROPOSED CUSTOMER RESPONSE:
{proposed_response}

Validate the proposed response using only the supplied evidence.

Return the required structured JSON.
"""

    try:
        result = await agent.run(task=task)

        final_content = ""

        for message in reversed(result.messages):

            content = getattr(message, "content", None)

            if isinstance(content, str) and content.strip():
                final_content = content
                break

        if not final_content:
            raise RuntimeError("Response Validation Agent returned no response.")

        try:
            parsed_result = json.loads(final_content)

        except json.JSONDecodeError as error:
            raise ValueError(
                f"Agent returned invalid JSON: {final_content}"
            ) from error

        # Basic output validation.
        allowed_statuses = {
            "approved",
            "needs_revision",
            "insufficient_evidence"
        }

        if parsed_result.get("validation_status") not in allowed_statuses:
            raise ValueError("Invalid validation_status returned by agent.")

        # ----------------------------------------------------
        # DETERMINISTIC ISSUE SYNCHRONISATION
        # ----------------------------------------------------

        issues = parsed_result.get("issues", [])
        unsupported_claims = parsed_result.get("unsupported_claims", [])

        if not isinstance(issues, list):
            issues = []

        if not isinstance(unsupported_claims, list):
            unsupported_claims = []

        corrected_response = str(parsed_result.get("validated_response") or "")
        parsed_result["issues"], parsed_result["unsupported_claims"] = (
            synchronize_validation_issues(issues, unsupported_claims, corrected_response)
        )

        
        
        # ----------------------------------------------------
        # DETERMINISTIC EVIDENCE TRACEABILITY
        # ----------------------------------------------------

        evidence_references = []

        organisation_id = organisation.get("id")

        for claim_item in parsed_result.get("supported_claims", []):
            reference = verify_claim_evidence(
                claim_item, web_findings, rag_passages, organisation_id
            )
            if reference:
                evidence_references.append(reference)

        unverified_supported_claims = []
        for claim_item in parsed_result.get("supported_claims", []):
            claim = claim_item.get("claim", "") if isinstance(claim_item, dict) else claim_item
            if claim and not any(ref.get("claim") == claim for ref in evidence_references):
                unverified_supported_claims.append(claim)
        if unverified_supported_claims:
            parsed_result["unsupported_claims"] = list(dict.fromkeys(
                parsed_result.get("unsupported_claims", []) + unverified_supported_claims
            ))
            parsed_result["issues"] = list(dict.fromkeys(
                parsed_result.get("issues", []) + [
                    f"No deterministic evidence passage could verify: {claim}"
                    for claim in unverified_supported_claims
                ]
            ))
            if parsed_result.get("validation_status") == "approved":
                parsed_result["validation_status"] = "insufficient_evidence"
                parsed_result["confidence"] = "low"
        parsed_result["evidence_references"] = evidence_references

        response_for_date_check = (
            parsed_result.get("validated_response") or proposed_response
        )
        date_issues = effective_date_contradictions(
            response_for_date_check, effective_date_findings, current_date_value
        )
        if date_issues:
            parsed_result["issues"] = list(dict.fromkeys(
                parsed_result.get("issues", []) + date_issues
            ))
            parsed_result["corrections_required"] = True
            if parsed_result.get("validation_status") == "approved":
                parsed_result["validation_status"] = "needs_revision"

                
        # ----------------------------------------------------
        # DETERMINISTIC FRESHNESS VALIDATION
        # ----------------------------------------------------

        if requires_current_verification(question):

            is_rbi_question = (
                "rbi" in question.lower()
                or "reserve bank of india" in question.lower()
                or "regulatory" in str(
                    organisation.get("regulator", "")
                ).lower()
            )

            if not has_full_source_content(
                web_findings,
                require_official_rbi=is_rbi_question
            ):

                parsed_result["validation_status"] = (
                    "insufficient_evidence"
                )

                parsed_result["confidence"] = "low"

                parsed_result["corrections_required"] = True

                parsed_result["issues"] = (
                    parsed_result.get("issues", []) +
                    [
                        "The question requires current or latest "
                        "information, but the supplied web research "
                        "contains search snippets rather than full "
                        "official source content."
                    ]
                )

                parsed_result["unsupported_claims"] = (
                    parsed_result.get("unsupported_claims", []) +
                    [
                        "Claims describing the latest applicable "
                        "RBI guidelines cannot be confirmed from "
                        "search snippets alone."
                    ]
                )

                regulator = str(organisation.get("regulator") or "the relevant regulator")
                organisation_name = str(organisation.get("name") or "the organisation")
                parsed_result["validated_response"] = (
                    f"I found relevant information, but the available evidence "
                    f"does not contain enough verified source information to "
                    f"confirm the latest applicable guidance for {organisation_name}. "
                    f"Please refer to official {regulator} notifications and "
                    "directions for confirmation."
                )

                parsed_result["validation_summary"] = (
                    "The response was not approved because current "
                    "regulatory information could not be verified "
                    "from the available source content."
                )

        return parsed_result

    finally:
        await model_client.close()

def extract_effective_dates(web_findings):
    """
    Extract dates that are explicitly described as effective dates
    in successfully retrieved web sources.
    """

    effective_dates = []

    patterns = [
        r"effective\s+(?:from|on|date\s+of)\s*[:\-]?\s*"
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4}|"
        r"[A-Za-z]+\s+\d{1,2},?\s+\d{4}|"
        r"\d{4}-\d{2}-\d{2})",

        r"(?:come|comes|coming)\s+into\s+force\s+"
        r"(?:with\s+effect\s+from\s+)?"
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4}|"
        r"[A-Za-z]+\s+\d{1,2},?\s+\d{4}|"
        r"\d{4}-\d{2}-\d{2})"
    ]

    for finding in web_findings:

        if not isinstance(finding, dict):
            continue

        if finding.get("retrieval_status") != "success":
            continue

        source_content = finding.get("source_content", "")

        if not isinstance(source_content, str):
            continue

        for pattern in patterns:
            matches = re.findall(
                pattern,
                source_content,
                flags=re.IGNORECASE
            )

            for matched_date in matches:
                parsed_date = parse_date(matched_date)
                if not parsed_date:
                    continue
                item = {
                    "date": matched_date,
                    "effective_date": parsed_date.isoformat(),
                    "source_title": finding.get("source_title", ""),
                    "source_url": finding.get("source_url", "")
                }
                if item not in effective_dates:
                    effective_dates.append(item)

    return effective_dates


def requires_current_verification(question):
    """
    Detect questions that require current or latest information.
    """

    keywords = [
        "latest",
        "current",
        "recent",
        "new guidelines",
        "updated guidelines",
        "as of today",
        "currently applicable"
    ]

    question = question.lower()

    return any(keyword in question for keyword in keywords)



def has_full_source_content(
    web_findings,
    require_official_rbi=False
):
    """
    Confirm that at least one source was successfully retrieved
    and contains meaningful source content.

    When require_official_rbi=True, the source must be hosted
    on an official RBI domain.
    """

    from urllib.parse import urlparse

    for finding in web_findings:

        if not isinstance(finding, dict):
            continue

        # Retrieval must have succeeded.
        if finding.get("retrieval_status") != "success":
            continue

        source_url = finding.get("source_url", "")

        if not source_url:
            continue

        parsed_url = urlparse(source_url)

        # Only accept HTTPS sources.
        if parsed_url.scheme != "https":
            continue

        hostname = (parsed_url.hostname or "").lower()

        # Require an official RBI domain when requested.
        if require_official_rbi:
            if not (
                hostname == "rbi.org.in"
                or hostname.endswith(".rbi.org.in")
            ):
                continue

        source_content = finding.get("source_content", "")

        if (
            isinstance(source_content, str)
            and len(source_content.strip()) > 200
        ):
            return True

    return False
