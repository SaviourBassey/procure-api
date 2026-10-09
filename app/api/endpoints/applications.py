

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.db.session import get_session
from app.dependencies import auth_deps
from app.models import (
    Account,
    ApplicationDocument,
    ApplicationItemQuote,
    ApplicationRequirementResponse,
    Tender,
    TenderApplication,
    TenderItem,
    TenderProductRequirement,
    VendorOnboarding,
)
from app.services.access import require_buyer

application_router = APIRouter()


def get_account_type(account: Account) -> str | None:
    data = getattr(account, "data", None) or {}

    if hasattr(data, "model_dump"):
        data = data.model_dump()

    if isinstance(data, dict):
        value = data.get("account_type")
        return str(value).lower() if value else None

    return None


def require_vendor(
    account: Account,
    session: Session,
) -> VendorOnboarding:
    if get_account_type(account) != "vendor":
        raise HTTPException(
            status_code=403,
            detail="Only vendor accounts can access these endpoints.",
        )

    vendor = session.exec(
        select(VendorOnboarding).where(
            VendorOnboarding.account_id == str(account.id)
        )
    ).first()

    if vendor is None:
        raise HTTPException(
            status_code=403,
            detail="Complete vendor onboarding first.",
        )

    return vendor


def get_owned_application(
    application_id: int,
    vendor: VendorOnboarding,
    session: Session,
) -> TenderApplication:
    application = session.exec(
        select(TenderApplication).where(
            TenderApplication.id == application_id,
            TenderApplication.vendor_onboarding_id == vendor.id,
        )
    ).first()

    if application is None:
        # Do not reveal another vendor's application.
        raise HTTPException(
            status_code=404,
            detail="Application not found.",
        )

    return application


def serialize_application(
    application: TenderApplication,
    tender: Tender,
    vendor: VendorOnboarding,
    session: Session,
    include_details: bool = False,
) -> dict:
    result = {
        "id": application.id,
        "tender_id": tender.id,
        "tender_title": tender.title,
        "tender_category": tender.category,
        "procurement_type": tender.procurement_type,
        "maximum_budget": str(tender.maximum_budget),
        "submission_deadline": tender.submission_deadline,
        "delivery_location": tender.delivery_location,
        "vendor_id": vendor.id,
        "vendor_business_name": vendor.business_name,
        "proposed_total_price": str(
            application.proposed_total_price
        ),
        "delivery_timeline": application.delivery_timeline,
        "proposal": application.proposal,
        "additional_notes": application.additional_notes,
        "status": application.status,
        "submitted_at": application.submitted_at,
    }

    if not include_details:
        return result

    # Quoted tender items
    quotes = session.exec(
        select(ApplicationItemQuote).where(
            ApplicationItemQuote.application_id == application.id
        )
    ).all()

    quote_details = []

    for quote in quotes:
        tender_item = session.get(
            TenderItem, quote.tender_item_id
        )

        if tender_item is not None:
            quote_details.append({
                "tender_item_id": tender_item.id,
                "item": tender_item.item,
                "quantity": str(tender_item.quantity),
                "unit": tender_item.unit,
                "unit_price": str(quote.unit_price),
                "total_price": str(quote.total_price),
            })

    result["item_quotes"] = quote_details

    # Responses to product requirements
    responses = session.exec(
        select(ApplicationRequirementResponse).where(
            ApplicationRequirementResponse.application_id
            == application.id
        )
    ).all()

    requirement_details = []

    for response in responses:
        requirement = session.get(
            TenderProductRequirement,
            response.requirement_id,
        )

        if requirement is not None:
            requirement_details.append({
                "requirement_id": requirement.id,
                "requirement_name": requirement.requirement_name,
                "required_value": requirement.value,
                "vendor_response": response.response,
            })

    result["requirement_responses"] = requirement_details

    # Uploaded supporting documents
    documents = session.exec(
        select(ApplicationDocument).where(
            ApplicationDocument.application_id == application.id
        )
    ).all()

    result["documents"] = [
        {
            "id": document.id,
            "name": document.name,
            "url": document.url,
            "file_format": document.file_format,
            "size_bytes": document.size_bytes,
        }
        for document in documents
    ]

    return result


@application_router.get(
    "/my-applications",
    tags=["Tender Applications"],
)
def get_my_applications(
    tender_id: int | None = Query(
        default=None,
        gt=0,
        description="Optionally filter applications by tender ID.",
    ),
    application_status: str | None = Query(
        default=None,
        alias="status",
        description="Optionally filter by application status.",
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_account: Account = Depends(
        auth_deps.get_current_account
    ),
    session: Session = Depends(get_session),
):
    vendor = require_vendor(current_account, session)

    statement = select(TenderApplication).where(
        TenderApplication.vendor_onboarding_id == vendor.id
    )

    if tender_id is not None:
        statement = statement.where(
            TenderApplication.tender_id == tender_id
        )

    if application_status:
        statement = statement.where(
            TenderApplication.status == application_status.lower()
        )

    applications = list(
        session.exec(
            statement
            .order_by(TenderApplication.submitted_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )

    results = []

    for application in applications:
        tender = session.get(Tender, application.tender_id)

        if tender is not None:
            results.append(
                serialize_application(
                    application=application,
                    tender=tender,
                    vendor=vendor,
                    session=session,
                    include_details=False,
                )
            )

    return {
        "count": len(results),
        "offset": offset,
        "limit": limit,
        "filters": {
            "tender_id": tender_id,
            "status": application_status,
        },
        "applications": results,
    }


@application_router.get(
    "/for-tender/{tender_id}",
    tags=["Tender Applications"],
)
def list_applications_for_tender(
    tender_id: int,
    current_account: Account = Depends(
        auth_deps.get_current_account
    ),
    session: Session = Depends(get_session),
):
    buyer = require_buyer(current_account, session)
    tender = session.get(Tender, tender_id)

    if tender is None or tender.buyer_onboarding_id != buyer.id:
        raise HTTPException(status_code=404, detail="Tender not found.")

    applications = list(
        session.exec(
            select(TenderApplication)
            .where(TenderApplication.tender_id == tender.id)
            .order_by(TenderApplication.submitted_at.desc())
        ).all()
    )

    results = []
    for application in applications:
        vendor = session.get(
            VendorOnboarding,
            application.vendor_onboarding_id,
        )
        if vendor is None:
            continue
        results.append(
            serialize_application(
                application=application,
                tender=tender,
                vendor=vendor,
                session=session,
                include_details=True,
            )
        )

    return {
        "tender_id": tender.id,
        "count": len(results),
        "applications": results,
    }


@application_router.get(
    "/{application_id}",
    tags=["Tender Applications"],
)
def get_application_details(
    application_id: int,
    current_account: Account = Depends(
        auth_deps.get_current_account
    ),
    session: Session = Depends(get_session),
):
    account_type = get_account_type(current_account)

    if account_type == "vendor":
        vendor = require_vendor(current_account, session)
        application = get_owned_application(
            application_id=application_id,
            vendor=vendor,
            session=session,
        )
    elif account_type == "buyer":
        buyer = require_buyer(current_account, session)
        application = session.get(TenderApplication, application_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found.")
        tender_owner = session.get(Tender, application.tender_id)
        if (
            tender_owner is None
            or tender_owner.buyer_onboarding_id != buyer.id
        ):
            raise HTTPException(status_code=404, detail="Application not found.")
        vendor = session.get(
            VendorOnboarding,
            application.vendor_onboarding_id,
        )
        if vendor is None:
            raise HTTPException(status_code=404, detail="Application not found.")
    else:
        raise HTTPException(
            status_code=403,
            detail="Only buyer and vendor accounts can view applications.",
        )

    tender = session.get(Tender, application.tender_id)

    if tender is None:
        raise HTTPException(
            status_code=404,
            detail="The tender associated with this application was not found.",
        )

    result = serialize_application(
        application=application,
        tender=tender,
        vendor=vendor,
        session=session,
        include_details=True,
    )

    return {
        "message": "Application details retrieved successfully.",
        "application": result,
    }
