from sqlmodel import Session, select

from app.models import (
    ApplicationAnalysis,
    ApplicationDocument,
    ApplicationItemQuote,
    ApplicationRequirementResponse,
    Tender,
    TenderApplication,
    TenderItem,
    TenderProductRequirement,
    TenderRequiredDocument,
    VendorOnboarding,
)
from app.services.analysis_engine import analyze_application, serialize_analysis


def load_application_bundle(session: Session, application: TenderApplication) -> dict:
    tender = session.get(Tender, application.tender_id)
    vendor = session.get(VendorOnboarding, application.vendor_onboarding_id)
    items = list(
        session.exec(
            select(TenderItem).where(TenderItem.tender_id == application.tender_id)
        ).all()
    )
    quotes = list(
        session.exec(
            select(ApplicationItemQuote).where(
                ApplicationItemQuote.application_id == application.id
            )
        ).all()
    )
    requirements = list(
        session.exec(
            select(TenderProductRequirement).where(
                TenderProductRequirement.tender_id == application.tender_id
            )
        ).all()
    )
    responses = list(
        session.exec(
            select(ApplicationRequirementResponse).where(
                ApplicationRequirementResponse.application_id == application.id
            )
        ).all()
    )
    required_documents = list(
        session.exec(
            select(TenderRequiredDocument).where(
                TenderRequiredDocument.tender_id == application.tender_id
            )
        ).all()
    )
    documents = list(
        session.exec(
            select(ApplicationDocument).where(
                ApplicationDocument.application_id == application.id
            )
        ).all()
    )
    return {
        "tender": tender,
        "vendor": vendor,
        "items": items,
        "quotes": quotes,
        "requirements": requirements,
        "responses": responses,
        "required_documents": required_documents,
        "documents": documents,
    }


def latest_analysis(session: Session, application_id: int) -> ApplicationAnalysis | None:
    return session.exec(
        select(ApplicationAnalysis)
        .where(ApplicationAnalysis.application_id == application_id)
        .order_by(ApplicationAnalysis.created_at.desc())
    ).first()


def run_and_store_analysis(session, application, buyer, requested_by):
    bundle = load_application_bundle(session, application)
    tender = bundle["tender"]
    vendor = bundle["vendor"]
    if tender is None or vendor is None:
        return None
    if tender.buyer_onboarding_id != buyer.id:
        return None
    return analyze_application(
        session,
        tender=tender,
        buyer=buyer,
        vendor=vendor,
        application=application,
        items=bundle["items"],
        quotes=bundle["quotes"],
        requirements=bundle["requirements"],
        responses=bundle["responses"],
        required_documents=bundle["required_documents"],
        documents=bundle["documents"],
        requested_by=requested_by,
    )


def public_analysis(row: ApplicationAnalysis) -> dict:
    return serialize_analysis(row)
