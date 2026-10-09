"""Rule-backed procurement analysis, narrated by the msflib AI layer.

Numeric scores, pass/fail results, and verification status come from the
rules in this module. The model writes the commentary. It does not get to
declare fraud or mark a vendor verified against a registry we did not query.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from msflib.ai_core.services.llm_json import LLMJSONParseError, parse_llm_json
from msflib.ai_core.tools.basic import calculator_tool, current_datetime_tool
from msflib.ai_core.tracking import TokenUsageCallback
from sqlmodel import Session

from app.core.config import settings
from app.models import (
    Account,
    ApplicationDocument,
    ApplicationItemQuote,
    ApplicationRequirementResponse,
    BuyerOnboarding,
    Tender,
    TenderApplication,
    TenderItem,
    TenderProductRequirement,
    TenderRequiredDocument,
    VendorOnboarding,
)
from app.services.access import as_utc

logger = logging.getLogger(__name__)

SECTION_ORDER = (
    "requirement_compliance",
    "technical_proposal",
    "financial",
    "cross_document_reconciliation",
    "vendor_identity",
    "document_integrity",
    "delivery_capability",
    "vendor_risk",
)

SECTION_TITLES = {
    "requirement_compliance": "Tender requirement compliance analysis",
    "technical_proposal": "Technical proposal analysis",
    "financial": "Financial and price analysis",
    "cross_document_reconciliation": "Cross-document reconciliation analysis",
    "vendor_identity": "Vendor identity and verification analysis",
    "document_integrity": "Document integrity and validity analysis",
    "delivery_capability": "Delivery and execution capability analysis",
    "vendor_risk": "Vendor risk assessment",
}

AMBIGUOUS_RESPONSES = {
    "n/a",
    "na",
    "tbd",
    "nil",
    "-",
    "see attached",
    "as above",
    "later",
}

SCORING_RULES = {
    "technical_score": (
        "Coverage score = round(100 * addressed product requirements / "
        "total product requirements). A requirement counts as addressed only "
        "when the vendor response is present and not an ambiguous placeholder. "
        "The score is null when the tender lists no product requirements. "
        "It measures response coverage, not an independent lab test of the goods."
    ),
    "financial_score": (
        "When line arithmetic matches and the total is within the maximum "
        "budget, financial_score = round(60 + 40 * (1 - total / maximum_budget)). "
        "A bid at the budget ceiling scores 60. A lower bid scores higher, up to 100. "
        "The score is null when arithmetic does not match. It is 0 when the total "
        "exceeds the budget. No cross-vendor price ranking is applied when only "
        "one bid is in the dossier."
    ),
    "risk": (
        "Severity is taken from observed evidence: a missing mandatory document "
        "or an arithmetic mismatch is high; an evidence gap such as an "
        "unverified identity is recorded as an unresolved gap and is not treated "
        "as proof of misconduct. Likelihood is 'observed' only when the dossier "
        "shows the condition, otherwise 'not_assessable'. Historical performance "
        "is not scored because this platform has no performance archive."
    ),
    "identity": (
        "Verified is reserved for a match against an official registry or "
        "approved verification provider. Submitted documents alone cannot "
        "produce Verified. This deployment does not call a registry, so "
        "independent verification is unavailable."
    ),
}

DISCLAIMER = (
    "Document inspection is separate from independent verification. "
    "A file that looks complete is not treated as genuine, and unusual "
    "formatting is not treated as fraud."
)


def _money(value: Decimal | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _calc(expression: str) -> Decimal:
    payload = calculator_tool().invoke({"expression": expression})
    if not isinstance(payload, dict) or "result" not in payload:
        raise ValueError(payload.get("error") if isinstance(payload, dict) else "calculator failed")
    return _money(payload["result"])


def _names_match(required_name: str, uploaded_name: str) -> bool:
    left = required_name.strip().lower()
    right = uploaded_name.strip().lower()
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _response_state(text: str | None) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return "missing"
    if cleaned.lower() in AMBIGUOUS_RESPONSES or len(cleaned) < 2:
        return "ambiguous"
    return "addressed"


def _finding(
    topic: str,
    result: str,
    evidence: str,
    severity: str = "none",
) -> dict[str, str]:
    return {
        "topic": topic,
        "result": result,
        "evidence": evidence,
        "severity": severity,
    }


def _compliance_status(findings: list[dict[str, str]]) -> str:
    results = {item["result"] for item in findings}
    if results <= {"pass"}:
        return "compliant"
    if "fail" in results and "pass" in results:
        return "partially_compliant"
    if "fail" in results:
        return "non_compliant"
    if "review" in results:
        return "requires_review"
    return "requires_review"


def build_evidence(
    *,
    tender: Tender,
    buyer: BuyerOnboarding,
    vendor: VendorOnboarding,
    application: TenderApplication,
    items: list[TenderItem],
    quotes: list[ApplicationItemQuote],
    requirements: list[TenderProductRequirement],
    responses: list[ApplicationRequirementResponse],
    required_documents: list[TenderRequiredDocument],
    documents: list[ApplicationDocument],
) -> dict[str, Any]:
    as_of = current_datetime_tool().invoke({"timezone": "UTC"})
    items_by_id = {item.id: item for item in items}
    responses_by_requirement = {row.requirement_id: row.response for row in responses}

    requirement_findings: list[dict[str, str]] = []
    matrix: list[dict[str, Any]] = []
    addressed = 0

    for requirement in requirements:
        response_text = responses_by_requirement.get(requirement.id)
        state = _response_state(response_text)
        if state == "addressed":
            addressed += 1
            requirement_findings.append(
                _finding(
                    requirement.requirement_name,
                    "pass",
                    f"Vendor response: {response_text}",
                )
            )
        elif state == "ambiguous":
            requirement_findings.append(
                _finding(
                    requirement.requirement_name,
                    "review",
                    f"Response is incomplete or a placeholder: {response_text!r}.",
                    "medium",
                )
            )
        else:
            requirement_findings.append(
                _finding(
                    requirement.requirement_name,
                    "fail",
                    "No response was submitted for this requirement.",
                    "high",
                )
            )
        matrix.append(
            {
                "requirement_id": requirement.id,
                "requirement_name": requirement.requirement_name,
                "required_value": requirement.value,
                "vendor_response": response_text,
                "match": state,
            }
        )

    document_findings: list[dict[str, str]] = []
    document_rows: list[dict[str, Any]] = []
    missing_documents: list[str] = []

    for required in required_documents:
        match = next(
            (
                document
                for document in documents
                if _names_match(required.name, document.name)
            ),
            None,
        )
        if match is None:
            missing_documents.append(required.name)
            document_findings.append(
                _finding(
                    required.name,
                    "fail",
                    "Required document was not uploaded.",
                    "high",
                )
            )
            document_rows.append(
                {
                    "name": required.name,
                    "status": "missing",
                    "issues": ["File was not submitted."],
                    "evidence": required.description,
                }
            )
        else:
            document_findings.append(
                _finding(
                    required.name,
                    "pass",
                    f"Uploaded as {match.name} ({match.file_format or 'unknown format'}).",
                )
            )

    for document in documents:
        issues: list[str] = []
        if not document.size_bytes:
            issues.append("File size was not recorded, so completeness is unknown.")
        document_rows.append(
            {
                "document_id": document.id,
                "name": document.name,
                "status": "submitted",
                "file_format": document.file_format,
                "size_bytes": document.size_bytes,
                "url": document.url,
                "issues": issues,
                "signature_checked": False,
                "expiry_checked": False,
                "verification_confidence": "low",
            }
        )

    names = [document.name.strip().lower() for document in documents]
    duplicate_names = sorted({name for name in names if names.count(name) > 1})

    deadline = as_utc(tender.submission_deadline)
    submitted_at = as_utc(application.submitted_at)
    deadline_met = submitted_at <= deadline
    requirement_findings.append(
        _finding(
            "Submission deadline",
            "pass" if deadline_met else "fail",
            (
                f"Submitted {submitted_at.isoformat()} against deadline "
                f"{deadline.isoformat()}."
            ),
            "none" if deadline_met else "high",
        )
    )

    quote_rows: list[dict[str, Any]] = []
    calculated_total = Decimal("0.00")
    arithmetic_exceptions: list[dict[str, Any]] = []
    quoted_item_ids = {quote.tender_item_id for quote in quotes}

    for item in items:
        if item.id not in quoted_item_ids:
            requirement_findings.append(
                _finding(
                    item.item,
                    "fail",
                    "Tender item has no quote.",
                    "high",
                )
            )

    for quote in quotes:
        item = items_by_id.get(quote.tender_item_id)
        if item is None:
            arithmetic_exceptions.append(
                {
                    "tender_item_id": quote.tender_item_id,
                    "issue": "Quote points at an item that is not on this tender.",
                }
            )
            continue
        expected = _calc(f"{item.quantity} * {quote.unit_price}")
        stored = _money(quote.total_price)
        matches = expected == stored
        calculated_total += expected
        if not matches:
            arithmetic_exceptions.append(
                {
                    "item": item.item,
                    "expected_total": str(expected),
                    "stated_total": str(stored),
                    "issue": "Line total does not match quantity times unit price.",
                }
            )
        quote_rows.append(
            {
                "tender_item_id": item.id,
                "item": item.item,
                "quantity": str(item.quantity),
                "unit": item.unit,
                "unit_price": str(_money(quote.unit_price)),
                "stated_total": str(stored),
                "calculated_total": str(expected),
                "arithmetic_match": matches,
            }
        )

    calculated_total = _money(calculated_total)
    stated_total = _money(application.proposed_total_price)
    if calculated_total != stated_total:
        arithmetic_exceptions.append(
            {
                "issue": "Sum of calculated line totals does not match the proposed total.",
                "calculated_total": str(calculated_total),
                "proposed_total_price": str(stated_total),
            }
        )

    budget = _money(tender.maximum_budget)
    within_budget = calculated_total <= budget
    requirement_findings.append(
        _finding(
            "Maximum budget",
            "pass" if within_budget else "fail",
            f"Calculated total {calculated_total} NGN against budget {budget} NGN.",
            "none" if within_budget else "high",
        )
    )
    requirement_findings.append(
        _finding(
            "Delivery timeline",
            "pass" if application.delivery_timeline.strip() else "fail",
            application.delivery_timeline or "No delivery timeline was provided.",
            "none" if application.delivery_timeline.strip() else "high",
        )
    )

    compliance_status = _compliance_status(requirement_findings)

    technical_score = None
    if requirements:
        technical_score = round(100 * addressed / len(requirements))

    deviations = [
        row
        for row in matrix
        if row["vendor_response"]
        and any(
            token in str(row["vendor_response"]).lower()
            for token in ("deviat", "alternative", "except", "cannot meet")
        )
    ]

    if arithmetic_exceptions:
        financial_score = None
        financial_status = "requires_review"
    elif not within_budget:
        financial_score = 0
        financial_status = "non_compliant"
    else:
        ratio = calculated_total / budget
        financial_score = int(
            (Decimal(60) + Decimal(40) * (Decimal(1) - ratio)).quantize(Decimal(1))
        )
        financial_status = "compliant"

    proposal = application.proposal or ""
    business_name = vendor.business_name.strip()
    name_in_proposal = bool(proposal) and business_name.lower() in proposal.lower()

    discrepancies: list[dict[str, Any]] = []
    if calculated_total != stated_total:
        discrepancies.append(
            {
                "field": "price",
                "values": [
                    {"source": "sum of line quotes", "value": str(calculated_total)},
                    {"source": "application.proposed_total_price", "value": str(stated_total)},
                ],
                "severity": "high",
                "clarification_required": True,
            }
        )
    if proposal and not name_in_proposal:
        discrepancies.append(
            {
                "field": "company_name",
                "values": [
                    {"source": "vendor onboarding", "value": business_name},
                    {
                        "source": "technical proposal",
                        "value": "Business name was not found in the proposal text.",
                    },
                ],
                "severity": "medium",
                "clarification_required": True,
            }
        )
    discrepancies.append(
        {
            "field": "registration_and_tax_identifiers",
            "values": [
                {
                    "source": "vendor profile",
                    "value": "Registration number, tax id, directors, and bank details are not stored.",
                }
            ],
            "severity": "low",
            "clarification_required": False,
            "note": "Nothing to reconcile until those fields are collected.",
        }
    )

    identity_mismatches = [row for row in discrepancies if row["field"] == "company_name"]
    if identity_mismatches:
        identity_status = "mismatch_detected"
        document_inspection = "mismatch_detected"
    elif not documents and not proposal:
        identity_status = "manual_verification_required"
        document_inspection = "insufficient_evidence"
    else:
        identity_status = "unavailable"
        document_inspection = "internally_consistent"

    risks: list[dict[str, Any]] = []

    def add_risk(
        risk_id: str,
        category: str,
        summary: str,
        severity: str,
        likelihood: str,
        impact: str,
        evidence: str,
        mitigation: str,
    ) -> None:
        risks.append(
            {
                "risk_id": risk_id,
                "category": category,
                "summary": summary,
                "severity": severity,
                "likelihood": likelihood,
                "impact": impact,
                "evidence": evidence,
                "mitigation": mitigation,
                "unresolved": True,
            }
        )

    if missing_documents:
        add_risk(
            "missing-documents",
            "documentation",
            "One or more required documents were not submitted.",
            "high",
            "observed",
            "The bid can fail a mandatory completeness check.",
            ", ".join(missing_documents),
            "Ask the vendor to upload each missing document before award.",
        )
    if arithmetic_exceptions:
        add_risk(
            "price-arithmetic",
            "financial",
            "Quoted figures are internally inconsistent.",
            "high",
            "observed",
            "The evaluated price may not be the price the vendor intends to charge.",
            str(arithmetic_exceptions),
            "Request a corrected pricing schedule before acceptance.",
        )
    if not within_budget:
        add_risk(
            "budget-overrun",
            "financial",
            "Calculated price exceeds the tender budget.",
            "high",
            "observed",
            "Awarding the bid would exceed the stated budget.",
            f"{calculated_total} > {budget}",
            "Reject the price or seek a revised quote within budget.",
        )
    add_risk(
        "identity-unverified",
        "identity",
        "The vendor has not been checked against an official registry.",
        "medium",
        "not_assessable",
        "The legal entity behind the bid is not independently confirmed.",
        "No registry lookup was performed. Onboarding stores business name and location only.",
        "Complete manual verification against the corporate registry before award. Do not treat uploaded files as proof of identity.",
    )
    add_risk(
        "delivery-capacity-unknown",
        "delivery",
        "No capacity, staffing, or logistics evidence was submitted.",
        "medium",
        "not_assessable",
        "The delivery timeline may not be feasible.",
        f"Delivery timeline text: {application.delivery_timeline}",
        "Ask for capacity, a milestone schedule, and any subcontractors before relying on the timeline.",
    )
    if not proposal.strip():
        add_risk(
            "proposal-gap",
            "technical",
            "No technical narrative was submitted.",
            "medium",
            "observed",
            "Specification matching cannot be checked beyond the structured responses.",
            "application.proposal is empty.",
            "Request a method statement if the tender needs one. The proposal field is optional in the current form.",
        )

    clarification_questions = []
    if missing_documents:
        clarification_questions.append(
            "Please upload the missing required documents: " + ", ".join(missing_documents) + "."
        )
    if not proposal.strip():
        clarification_questions.append(
            "Describe the delivery method, milestones, and any subcontractors."
        )
    clarification_questions.append(
        "Confirm the legal business name, registration number, and the person authorized to sign."
    )

    technical_status = "requires_review"
    if requirements:
        if addressed == len(requirements) and not deviations:
            technical_status = "compliant"
        elif addressed == 0:
            technical_status = "non_compliant"
        else:
            technical_status = "partially_compliant"

    sections = {
        "requirement_compliance": {
            "status": compliance_status,
            "summary": "",
            "findings": requirement_findings,
            "score": None,
            "details": {
                "mandatory_checks": requirement_findings,
                "optional_notes": tender.optional_notes,
            },
        },
        "technical_proposal": {
            "status": technical_status,
            "summary": "",
            "findings": [
                _finding(
                    row["requirement_name"],
                    "pass" if row["match"] == "addressed" else "review" if row["match"] == "ambiguous" else "fail",
                    f"Required: {row['required_value']}. Response: {row['vendor_response'] or 'missing'}.",
                )
                for row in matrix
            ],
            "score": technical_score,
            "details": {
                "compliance_matrix": matrix,
                "deviations": deviations,
                "strengths": [],
                "weaknesses": [],
                "technical_score": technical_score,
                "scoring_rule": SCORING_RULES["technical_score"],
            },
        },
        "financial": {
            "status": financial_status,
            "summary": "",
            "findings": [
                _finding(
                    "Evaluated bid price",
                    "pass" if within_budget and not arithmetic_exceptions else "fail" if not within_budget else "review",
                    f"Evaluated price {calculated_total} NGN. Budget {budget} NGN.",
                    "none" if within_budget and not arithmetic_exceptions else "high",
                )
            ],
            "score": financial_score,
            "details": {
                "currency": "NGN",
                "currency_note": "No currency or exchange rate was declared. Amounts are treated as NGN.",
                "normalized_cost_breakdown": quote_rows,
                "evaluated_bid_price": str(calculated_total),
                "stated_total": str(stated_total),
                "maximum_budget": str(budget),
                "within_budget": within_budget,
                "pricing_exceptions": arithmetic_exceptions
                + [
                    {
                        "issue": "Taxes, fees, transportation, installation, discounts, and payment milestones were not itemized.",
                    }
                ],
                "other_vendor_comparison": "No other priced bids were included in this analysis.",
                "total_cost_of_ownership": "Operating and maintenance costs were not provided.",
                "financial_score": financial_score,
                "scoring_rule": SCORING_RULES["financial_score"],
            },
        },
        "cross_document_reconciliation": {
            "status": "requires_review" if any(row.get("clarification_required") for row in discrepancies if row["field"] != "registration_and_tax_identifiers") else "compliant",
            "summary": "",
            "findings": [
                _finding(
                    row["field"],
                    "review" if row.get("clarification_required") else "pass",
                    str(row["values"]),
                    row["severity"],
                )
                for row in discrepancies
            ],
            "score": None,
            "details": {"discrepancies": discrepancies},
        },
        "vendor_identity": {
            "status": identity_status,
            "summary": "",
            "findings": [
                _finding(
                    "Independent registry check",
                    "review",
                    "No official registry or approved verification provider was queried.",
                    "medium",
                ),
                _finding(
                    "Declared business name",
                    "pass" if not identity_mismatches else "review",
                    f"Onboarding business name: {business_name}. Location: {vendor.location}.",
                    "none" if not identity_mismatches else "medium",
                ),
            ],
            "score": None,
            "details": {
                "verification_status": identity_status,
                "independent_verification": "unavailable",
                "document_inspection": document_inspection,
                "business_name": business_name,
                "location": vendor.location,
                "buyer_organization": buyer.organization_name,
                "note": SCORING_RULES["identity"],
            },
        },
        "document_integrity": {
            "status": "non_compliant" if missing_documents else "requires_review",
            "summary": "",
            "findings": document_findings
            + (
                [
                    _finding(
                        "Duplicate filenames",
                        "review",
                        ", ".join(duplicate_names),
                        "low",
                    )
                ]
                if duplicate_names
                else []
            ),
            "score": None,
            "details": {
                "documents": document_rows,
                "missing_documents": missing_documents,
                "duplicate_names": duplicate_names,
                "verification_confidence": "low",
                "suspected_fraud": False,
                "fraud_determination": "not_made",
                "limitations": (
                    "Signatures, stamps, expiry dates, metadata, and digital signatures "
                    "were not inspected. File contents were not extracted."
                ),
            },
        },
        "delivery_capability": {
            "status": "requires_review",
            "summary": "",
            "findings": [
                _finding(
                    "Delivery timeline",
                    "review",
                    application.delivery_timeline,
                    "medium",
                ),
                _finding(
                    "Capacity evidence",
                    "review",
                    "Staffing, equipment, subcontracting, and spare-parts plans were not requested as structured fields.",
                    "medium",
                ),
            ],
            "score": None,
            "details": {
                "feasibility": "requires_review",
                "delivery_timeline": application.delivery_timeline,
                "delivery_location": tender.delivery_location,
                "schedule_risks": [
                    "No milestone schedule was submitted, so the timeline cannot be checked against capacity."
                ],
                "unsupported_commitments": (
                    [proposal.strip()] if proposal.strip() else []
                ),
                "clarification_questions": clarification_questions,
            },
        },
        "vendor_risk": {
            "status": "requires_review" if risks else "compliant",
            "summary": "",
            "findings": [
                _finding(
                    risk["risk_id"],
                    "review",
                    risk["evidence"],
                    risk["severity"],
                )
                for risk in risks
            ],
            "score": None,
            "details": {
                "risks": risks,
                "scoring_rule": SCORING_RULES["risk"],
                "historical_performance": "unavailable",
            },
        },
    }

    return {
        "as_of": as_of,
        "currency": "NGN",
        "scoring_rules": SCORING_RULES,
        "disclaimer": DISCLAIMER,
        "dossier": {
            "tender_id": tender.id,
            "tender_title": tender.title,
            "buyer_organization": buyer.organization_name,
            "vendor_business_name": business_name,
            "application_id": application.id,
            "submitted_at": submitted_at.isoformat(),
        },
        "sections": sections,
    }


def _message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
        return "\n".join(part for part in parts if part)
    return str(content)


def _llm():
    from msflib.ai_core.deps import get_ai_dependencies

    ai_settings = settings.scope("AI_CORE")
    api_key = str(getattr(ai_settings, "LLM_API_KEY", "") or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI analysis is not configured. Set LLM_API_KEY and LLM_PROVIDER "
                "(for example LLM_PROVIDER=openrouter) and try again."
            ),
        )
    return get_ai_dependencies(settings).get_llm(), ai_settings


def _narrative_from_model(evidence: dict[str, Any]) -> tuple[dict[str, Any], TokenUsageCallback, str, str]:
    from langchain_core.messages import HumanMessage, SystemMessage

    llm, ai_settings = _llm()
    usage = TokenUsageCallback()
    system = SystemMessage(
        content=(
            "You are ProcureGuard, a procurement analyst. You receive a rule-based "
            "evidence pack. Write commentary only. Do not change statuses, scores, "
            "prices, or verification results. Do not declare fraud. Do not say the "
            "vendor is verified against a registry. Independent verification is "
            "unavailable. Reply with one JSON object and no markdown."
        )
    )
    human = HumanMessage(
        content=(
            "Return JSON with this shape:\n"
            "{\n"
            '  "summaries": {"requirement_compliance": "", "technical_proposal": "", '
            '"financial": "", "cross_document_reconciliation": "", "vendor_identity": "", '
            '"document_integrity": "", "delivery_capability": "", "vendor_risk": ""},\n'
            '  "technical": {"strengths": [], "weaknesses": []},\n'
            '  "delivery_questions": [],\n'
            '  "risk_mitigations": [{"risk_id": "", "mitigation": ""}]\n'
            "}\n"
            "Use only the evidence below. Keep each summary under 80 words.\n\n"
            f"{evidence}"
        )
    )
    try:
        message = llm.invoke([system, human], config={"callbacks": [usage]})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Procurement analysis model call failed")
        detail = "The analysis model could not complete this review."
        text = str(exc).lower()
        if "api key" in text or "unauthorized" in text or "401" in text:
            detail = "The analysis model rejected the configured API key."
        raise HTTPException(status_code=502, detail=detail) from exc

    try:
        parsed = parse_llm_json(_message_text(message))
    except LLMJSONParseError as exc:
        raise HTTPException(
            status_code=502,
            detail="The analysis model returned a response that was not valid JSON.",
        ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=502,
            detail="The analysis model did not return a JSON object.",
        )

    provider = str(getattr(ai_settings, "LLM_PROVIDER", "") or "")
    model_name = str(getattr(ai_settings, "LLM_MODEL", "") or "")
    return parsed, usage, provider, model_name


def _clean_summary(section_key: str, summary: str) -> str:
    text = (summary or "").strip()
    if section_key == "document_integrity" and "fraud" in text.lower():
        text = (
            "Fraud was not determined. Unusual formatting is not evidence of fraud. "
            + text
        )
    if section_key == "vendor_identity" and "verified" in text.lower():
        text = (
            "Independent verification is unavailable, so this vendor is not Verified. "
            + text
        )
    return text


def assemble_report(evidence: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
    summaries = narrative.get("summaries") if isinstance(narrative.get("summaries"), dict) else {}
    technical = narrative.get("technical") if isinstance(narrative.get("technical"), dict) else {}
    mitigations = narrative.get("risk_mitigations") if isinstance(narrative.get("risk_mitigations"), list) else []
    extra_questions = narrative.get("delivery_questions") if isinstance(narrative.get("delivery_questions"), list) else []

    mitigation_by_id = {}
    for item in mitigations:
        if isinstance(item, dict) and item.get("risk_id"):
            mitigation_by_id[str(item["risk_id"])] = str(item.get("mitigation") or "").strip()

    strengths = [str(item) for item in technical.get("strengths") or [] if str(item).strip()]
    weaknesses = [str(item) for item in technical.get("weaknesses") or [] if str(item).strip()]

    ordered = []
    for key in SECTION_ORDER:
        section = dict(evidence["sections"][key])
        section["key"] = key
        section["title"] = SECTION_TITLES[key]
        section["summary"] = _clean_summary(key, str(summaries.get(key) or ""))
        if not section["summary"]:
            finding_text = "; ".join(
                finding["evidence"] for finding in section["findings"][:3]
            )
            section["summary"] = finding_text or "No additional narrative was returned."

        details = dict(section.get("details") or {})
        if key == "technical_proposal":
            details["strengths"] = strengths
            details["weaknesses"] = weaknesses
        if key == "delivery_capability":
            questions = list(details.get("clarification_questions") or [])
            for question in extra_questions:
                text = str(question).strip()
                if text and text not in questions:
                    questions.append(text)
            details["clarification_questions"] = questions
        if key == "vendor_risk":
            risks = []
            for risk in details.get("risks") or []:
                updated = dict(risk)
                extra = mitigation_by_id.get(updated["risk_id"])
                if extra:
                    updated["mitigation"] = extra
                risks.append(updated)
            details["risks"] = risks
        if key == "vendor_identity":
            details["verification_status"] = section["status"]
            details["independent_verification"] = "unavailable"
        if key == "document_integrity":
            details["suspected_fraud"] = False
            details["fraud_determination"] = "not_made"
        section["details"] = details
        ordered.append(section)

    return {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": evidence["disclaimer"],
        "scoring_rules": evidence["scoring_rules"],
        "dossier": evidence["dossier"],
        "sections": ordered,
    }


def analyze_application(
    session: Session,
    *,
    tender: Tender,
    buyer: BuyerOnboarding,
    vendor: VendorOnboarding,
    application: TenderApplication,
    items: list[TenderItem],
    quotes: list[ApplicationItemQuote],
    requirements: list[TenderProductRequirement],
    responses: list[ApplicationRequirementResponse],
    required_documents: list[TenderRequiredDocument],
    documents: list[ApplicationDocument],
    requested_by: Account,
) -> dict[str, Any]:
    from app.models.analysis import ApplicationAnalysis

    evidence = build_evidence(
        tender=tender,
        buyer=buyer,
        vendor=vendor,
        application=application,
        items=items,
        quotes=quotes,
        requirements=requirements,
        responses=responses,
        required_documents=required_documents,
        documents=documents,
    )
    narrative, usage, provider, model_name = _narrative_from_model(evidence)
    report = assemble_report(evidence, narrative)

    row = ApplicationAnalysis(
        application_id=application.id,
        tender_id=tender.id,
        requested_by_account_id=requested_by.id,
        provider=provider,
        model=model_name,
        report=report,
        prompt_tokens=usage.prompt_tokens or None,
        completion_tokens=usage.completion_tokens or None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return serialize_analysis(row)


def serialize_analysis(row: Any) -> dict[str, Any]:
    report = row.report or {}
    return {
        "id": row.id,
        "application_id": row.application_id,
        "tender_id": row.tender_id,
        "provider": row.provider,
        "model": row.model,
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "created_at": row.created_at,
        "disclaimer": report.get("disclaimer"),
        "scoring_rules": report.get("scoring_rules"),
        "dossier": report.get("dossier"),
        "sections": report.get("sections") or [],
    }
