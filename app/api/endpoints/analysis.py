from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db.session import get_session
from app.dependencies import auth_deps
from app.models import Account, BuyerOnboarding, Tender, TenderApplication
from app.services.access import require_buyer
from app.services.application_context import (
    latest_analysis,
    public_analysis,
    run_and_store_analysis,
)

analysis_router = APIRouter()


def _buyer_application(
    application_id: int,
    buyer: BuyerOnboarding,
    session: Session,
) -> tuple[TenderApplication, Tender]:
    application = session.get(TenderApplication, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")

    tender = session.get(Tender, application.tender_id)
    if tender is None or tender.buyer_onboarding_id != buyer.id:
        raise HTTPException(status_code=404, detail="Application not found.")

    return application, tender


@analysis_router.post(
    "/{application_id}/analysis",
    tags=["Procurement Analysis"],
)
def analyze_applicant(
    application_id: int,
    current_account: Account = Depends(auth_deps.get_current_account),
    session: Session = Depends(get_session),
):
    buyer = require_buyer(current_account, session)
    application, _tender = _buyer_application(application_id, buyer, session)
    report = run_and_store_analysis(
        session,
        application,
        buyer,
        current_account,
    )
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="The tender or vendor for this application was not found.",
        )
    return {
        "message": "Applicant analysis completed.",
        "analysis": report,
    }


@analysis_router.get(
    "/{application_id}/analysis",
    tags=["Procurement Analysis"],
)
def get_applicant_analysis(
    application_id: int,
    current_account: Account = Depends(auth_deps.get_current_account),
    session: Session = Depends(get_session),
):
    buyer = require_buyer(current_account, session)
    _buyer_application(application_id, buyer, session)
    row = latest_analysis(session, application_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="No analysis has been run for this application.",
        )
    return {
        "message": "Latest applicant analysis.",
        "analysis": public_analysis(row),
    }
