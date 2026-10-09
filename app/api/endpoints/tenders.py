
from typing import Literal

import json
from decimal import Decimal

from pydantic import ValidationError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from fastapi import (
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)

from app.db.session import get_session
from app.dependencies import auth_deps
from app.models import (
    Account,
    BuyerOnboarding,
    Tender,
    TenderItem,
    TenderProductRequirement,
    TenderRequiredDocument,
)
from app.models import (
    Account,
    BuyerOnboarding,
    Tender,
    TenderItem,
    TenderProductRequirement,
    VendorOnboarding,
    TenderApplication,
    ApplicationItemQuote,
    ApplicationRequirementResponse,
    ApplicationDocument,
)
from app.schemas.tender import TenderCreate

from app.schemas.application import TenderApplicationCreate

from app.services.cloudinary_storage import upload_file

from datetime import datetime, timezone


tender_router = APIRouter()


def get_account_type(account: Account) -> str | None:
    data = getattr(account, "data", None) or {}

    if hasattr(data, "model_dump"):
        data = data.model_dump()

    if isinstance(data, dict):
        value = data.get("account_type")
        return str(value).lower() if value else None

    return None


@tender_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    tags=["Tenders"],
)
def create_tender(
    payload: TenderCreate,
    current_account: Account = Depends(
        auth_deps.get_current_account
    ),
    session: Session = Depends(get_session),
):
    # Only buyer accounts can create tenders.
    if get_account_type(current_account) != "buyer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only buyer accounts can create tenders.",
        )

    # A buyer must complete onboarding first.
    buyer = session.exec(
        select(BuyerOnboarding).where(
            BuyerOnboarding.account_id == str(current_account.id)
        )
    ).first()

    if buyer is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Complete buyer onboarding before creating a tender.",
        )

    tender = Tender(
        buyer_onboarding_id=buyer.id,
        title=payload.title.strip(),
        category=payload.category.strip(),
        procurement_type=payload.procurement_type.strip(),
        maximum_budget=payload.maximum_budget,
        submission_deadline=payload.submission_deadline,
        delivery_location=payload.delivery_location.strip(),
        optional_description=(
            payload.optional_description.strip()
            if payload.optional_description
            else None
        ),
        optional_notes=(
            payload.optional_notes.strip()
            if payload.optional_notes
            else None
        ),
        status="open",
    )

    try:
        session.add(tender)
        session.flush()

        for item in payload.items:
            session.add(
                TenderItem(
                    tender_id=tender.id,
                    item=item.item.strip(),
                    quantity=item.quantity,
                    unit=item.unit.strip(),
                )
            )

        for requirement in payload.product_requirements:
            session.add(
                TenderProductRequirement(
                    tender_id=tender.id,
                    requirement_name=requirement.requirement_name.strip(),
                    value=requirement.value.strip(),
                )
            )

        for document in payload.required_documents:
            session.add(
                TenderRequiredDocument(
                    tender_id=tender.id,
                    name=document.name.strip(),
                    description=(
                        document.description.strip()
                        if document.description
                        else None
                    ),
                )
            )

        # Save the tender and all its child records together.
        session.commit()
        session.refresh(tender)

    except Exception:
        session.rollback()
        raise

    return {
        "message": "Tender created successfully.",
        "tender": {
            "id": tender.id,
            "title": tender.title,
            "category": tender.category,
            "procurement_type": tender.procurement_type,
            "maximum_budget": tender.maximum_budget,
            "submission_deadline": tender.submission_deadline,
            "delivery_location": tender.delivery_location,
            "optional_description": tender.optional_description,
            "optional_notes": tender.optional_notes,
            "status": tender.status,
            "buyer_organization": buyer.organization_name,
            "items": [
                {
                    "item": item.item,
                    "quantity": item.quantity,
                    "unit": item.unit,
                }
                for item in payload.items
            ],
            "product_requirements": [
                {
                    "requirement_name": requirement.requirement_name,
                    "value": requirement.value,
                }
                for requirement in payload.product_requirements
            ],
            "required_documents": [
                {
                    "name": document.name,
                    "description": document.description,
                }
                for document in payload.required_documents
            ],
            "created_at": tender.created_at,
        },
    }






def tender_to_dict(
    tender: Tender,
    items: list[TenderItem],
    requirements: list[TenderProductRequirement],
    documents: list[TenderRequiredDocument],
    buyer_organization: str | None = None,
) -> dict:
    return {
        "id": tender.id,
        "title": tender.title,
        "category": tender.category,
        "procurement_type": tender.procurement_type,
        "maximum_budget": tender.maximum_budget,
        "submission_deadline": tender.submission_deadline,
        "delivery_location": tender.delivery_location,
        "optional_description": tender.optional_description,
        "optional_notes": tender.optional_notes,
        "status": tender.status,
        "buyer_organization": buyer_organization,
        "items": [
            {
                "id": item.id,
                "item": item.item,
                "quantity": item.quantity,
                "unit": item.unit,
            }
            for item in items
        ],
        "product_requirements": [
            {
                "id": requirement.id,
                "requirement_name": requirement.requirement_name,
                "value": requirement.value,
            }
            for requirement in requirements
        ],
        "required_documents": [
            {
                "id": document.id,
                "name": document.name,
                "description": document.description,
            }
            for document in documents
        ],
        "created_at": tender.created_at,
    }


def load_tender_details(
    session: Session,
    tenders: list[Tender],
) -> list[dict]:
    if not tenders:
        return []

    tender_ids = [tender.id for tender in tenders]

    items = session.exec(
        select(TenderItem).where(
            TenderItem.tender_id.in_(tender_ids)
        )
    ).all()

    requirements = session.exec(
        select(TenderProductRequirement).where(
            TenderProductRequirement.tender_id.in_(tender_ids)
        )
    ).all()

    documents = session.exec(
        select(TenderRequiredDocument).where(
            TenderRequiredDocument.tender_id.in_(tender_ids)
        )
    ).all()

    items_by_tender: dict[int, list[TenderItem]] = {}
    requirements_by_tender: dict[
        int, list[TenderProductRequirement]
    ] = {}
    documents_by_tender: dict[
        int, list[TenderRequiredDocument]
    ] = {}

    for item in items:
        items_by_tender.setdefault(item.tender_id, []).append(item)

    for requirement in requirements:
        requirements_by_tender.setdefault(
            requirement.tender_id, []
        ).append(requirement)

    for document in documents:
        documents_by_tender.setdefault(
            document.tender_id, []
        ).append(document)

    return [
        tender_to_dict(
            tender,
            items_by_tender.get(tender.id, []),
            requirements_by_tender.get(tender.id, []),
            documents_by_tender.get(tender.id, []),
        )
        for tender in tenders
    ]


@tender_router.get("/my-tenders", tags=["Tenders"])
def get_my_tenders(
    tender_status: Literal["active", "closed"] | None = Query(
        default=None,
        alias="status",
        description="Optional filter: active or closed.",
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_account: Account = Depends(
        auth_deps.get_current_account
    ),
    session: Session = Depends(get_session),
):
    if get_account_type(current_account) != "buyer":
        raise HTTPException(
            status_code=403,
            detail="Only buyer accounts can view their tenders.",
        )

    buyer = session.exec(
        select(BuyerOnboarding).where(
            BuyerOnboarding.account_id == str(current_account.id)
        )
    ).first()

    if buyer is None:
        raise HTTPException(
            status_code=403,
            detail="Complete buyer onboarding first.",
        )

    statement = select(Tender).where(
        Tender.buyer_onboarding_id == buyer.id
    )

    if tender_status == "active":
        statement = statement.where(
            Tender.status.in_(["open", "active"])
        )
    elif tender_status == "closed":
        statement = statement.where(
            Tender.status == "closed"
        )

    statement = (
        statement
        .order_by(Tender.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    tenders = list(session.exec(statement).all())
    results = load_tender_details(session, tenders)

    # Include the buyer's organization name in their own results.
    for tender_data in results:
        tender_data["buyer_organization"] = buyer.organization_name

    return {
        "count": len(results),
        "offset": offset,
        "limit": limit,
        "status_filter": tender_status,
        "tenders": results,
    }


@tender_router.get("/active", tags=["Tenders"])
def get_active_tenders(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_account: Account = Depends(
        auth_deps.get_current_account
    ),
    session: Session = Depends(get_session),
):
    if get_account_type(current_account) != "vendor":
        raise HTTPException(
            status_code=403,
            detail="Only vendor accounts can browse active tenders.",
        )

    statement = (
        select(Tender)
        .where(
            Tender.submission_deadline > datetime.now(timezone.utc)
        )
        .order_by(Tender.submission_deadline.asc())
        .offset(offset)
        .limit(limit)
    )

    tenders = list(session.exec(statement).all())
    results = load_tender_details(session, tenders)

    # Include the buyer organization that published each tender.
    buyer_ids = list({
        tender.buyer_onboarding_id for tender in tenders
    })

    if buyer_ids:
        buyers = session.exec(
            select(BuyerOnboarding).where(
                BuyerOnboarding.id.in_(buyer_ids)
            )
        ).all()

        organizations = {
            buyer.id: buyer.organization_name for buyer in buyers
        }

        for tender, tender_data in zip(tenders, results):
            tender_data["buyer_organization"] = organizations.get(
                tender.buyer_onboarding_id
            )

    return {
        "count": len(results),
        "offset": offset,
        "limit": limit,
        "tenders": results,
    }



@tender_router.get("/{tender_id}", tags=["Tenders"])
def get_tender_details(
    tender_id: int,
    current_account: Account = Depends(
        auth_deps.get_current_account
    ),
    session: Session = Depends(get_session),
):
    account_type = get_account_type(current_account)

    # 1. Fetch the tender
    tender = session.exec(
        select(Tender).where(Tender.id == tender_id)
    ).first()

    if tender is None:
        raise HTTPException(
            status_code=404,
            detail="Tender not found.",
        )

    # 2. Get the buyer who owns the tender
    buyer = session.get(
        BuyerOnboarding,
        tender.buyer_onboarding_id,
    )

    if buyer is None:
        raise HTTPException(
            status_code=404,
            detail="Tender owner not found.",
        )

    # 3. Apply role-based access rules
    if account_type == "buyer":
        # Buyers can only view tenders they created.
        if buyer.account_id != str(current_account.id):
            raise HTTPException(
                status_code=403,
                detail="You can only view your own tenders.",
            )

    elif account_type == "vendor":
        # Vendors can only view active, non-expired tenders.
        now = datetime.now(timezone.utc)

        if (
            tender.status not in ["open", "active"]
            or tender.submission_deadline <= now
        ):
            raise HTTPException(
                status_code=404,
                detail="Active tender not found.",
            )

    else:
        raise HTTPException(
            status_code=403,
            detail="Only buyer and vendor accounts can view tenders.",
        )

    # 4. Load the tender and its related records
    results = load_tender_details(session, [tender])
    tender_data = results[0]
    tender_data["buyer_organization"] = buyer.organization_name

    return {
        "message": "Tender details retrieved successfully.",
        "tender": tender_data,
    }



@tender_router.post(
    "/{tender_id}/apply",
    status_code=status.HTTP_201_CREATED,
    tags=["Tender Applications"],
)
def apply_to_tender(
    tender_id: int,
    application_data: str = Form(...),
    document_names: list[str] = Form(default=[]),
    documents: list[UploadFile] | None = File(default=None),
    current_account: Account = Depends(
        auth_deps.get_current_account
    ),
    session: Session = Depends(get_session),
):
    # 1. Ensure this is a vendor account
    if get_account_type(current_account) != "vendor":
        raise HTTPException(
            status_code=403,
            detail="Only vendor accounts can apply to tenders.",
        )

    # 2. Get the vendor's completed onboarding profile
    vendor = session.exec(
        select(VendorOnboarding).where(
            VendorOnboarding.account_id == str(current_account.id)
        )
    ).first()

    if vendor is None:
        raise HTTPException(
            status_code=403,
            detail="Complete vendor onboarding before applying.",
        )

    # 3. Validate the submitted JSON
    try:
        payload = TenderApplicationCreate.model_validate(
            json.loads(application_data)
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=422,
            detail="Invalid application_data. Check the required fields and JSON format.",
        ) from exc

    # 4. Get the tender and check its deadline/status
    tender = session.get(Tender, tender_id)

    if tender is None:
        raise HTTPException(
            status_code=404,
            detail="Tender not found.",
        )

    now = datetime.now(timezone.utc)

    if (
        tender.status not in ["open", "active"]
        or tender.submission_deadline <= now
    ):
        raise HTTPException(
            status_code=400,
            detail="This tender is closed or its submission deadline has passed.",
        )

    # 5. Prevent duplicate applications
    existing_application = session.exec(
        select(TenderApplication).where(
            TenderApplication.tender_id == tender_id,
            TenderApplication.vendor_onboarding_id == vendor.id,
        )
    ).first()

    if existing_application:
        raise HTTPException(
            status_code=409,
            detail="You have already applied to this tender.",
        )

    # 6. Verify every tender item is quoted exactly once
    tender_items = session.exec(
        select(TenderItem).where(
            TenderItem.tender_id == tender_id
        )
    ).all()

    tender_items_by_id = {
        item.id: item for item in tender_items
    }

    submitted_item_ids = [
        quote.tender_item_id for quote in payload.item_quotes
    ]

    if len(submitted_item_ids) != len(set(submitted_item_ids)):
        raise HTTPException(
            status_code=422,
            detail="Each tender item can only be quoted once.",
        )

    if set(submitted_item_ids) != set(tender_items_by_id):
        raise HTTPException(
            status_code=422,
            detail="You must quote every tender item and cannot include unrelated items.",
        )

    # 7. Validate requirement responses belong to this tender
    requirements = session.exec(
        select(TenderProductRequirement).where(
            TenderProductRequirement.tender_id == tender_id
        )
    ).all()

    requirements_by_id = {
        requirement.id: requirement
        for requirement in requirements
    }

    submitted_requirement_ids = [
        response.requirement_id
        for response in payload.requirement_responses
    ]

    if len(submitted_requirement_ids) != len(
        set(submitted_requirement_ids)
    ):
        raise HTTPException(
            status_code=422,
            detail="Each product requirement can only be answered once.",
        )

    if not set(submitted_requirement_ids).issubset(
        set(requirements_by_id)
    ):
        raise HTTPException(
            status_code=422,
            detail="One or more requirement IDs do not belong to this tender.",
        )

    # 8. Validate document fields
    uploaded_documents = documents or []

    if len(document_names) != len(uploaded_documents):
        raise HTTPException(
            status_code=422,
            detail="Provide one document name for every uploaded file.",
        )

    if any(not name.strip() for name in document_names):
        raise HTTPException(
            status_code=422,
            detail="Document names cannot be empty.",
        )

    # 9. Calculate the total from the actual tender quantities
    total_price = Decimal("0.00")
    quote_rows = []

    for quote in payload.item_quotes:
        tender_item = tender_items_by_id[quote.tender_item_id]
        line_total = (
            tender_item.quantity * quote.unit_price
        ).quantize(Decimal("0.01"))

        total_price += line_total

        quote_rows.append(
            ApplicationItemQuote(
                tender_item_id=tender_item.id,
                unit_price=quote.unit_price,
                total_price=line_total,
            )
        )

    total_price = total_price.quantize(Decimal("0.01"))

    # Optional business rule: prevent quotations above the budget.
    if total_price > tender.maximum_budget:
        raise HTTPException(
            status_code=422,
            detail="Your total quotation exceeds the tender's maximum budget.",
        )

    # 10. Upload files and save the application atomically in the DB
    try:
        application = TenderApplication(
            tender_id=tender.id,
            vendor_onboarding_id=vendor.id,
            proposed_total_price=total_price,
            delivery_timeline=payload.delivery_timeline,
            proposal=payload.proposal,
            additional_notes=payload.additional_notes,
            status="submitted",
        )

        session.add(application)
        session.flush()

        for quote_row in quote_rows:
            quote_row.application_id = application.id
            session.add(quote_row)

        for response in payload.requirement_responses:
            session.add(
                ApplicationRequirementResponse(
                    application_id=application.id,
                    requirement_id=response.requirement_id,
                    response=response.response,
                )
            )

        for name, uploaded_file in zip(
            document_names, uploaded_documents
        ):
            result = upload_file(
                uploaded_file,
                folder=(
                    f"procure/applications/{application.id}"
                ),
                allowed_types={
                    "application/pdf",
                    "image/jpeg",
                    "image/png",
                },
            )

            session.add(
                ApplicationDocument(
                    application_id=application.id,
                    name=name.strip(),
                    url=result["url"],
                    public_id=result["public_id"],
                    file_format=result.get("format"),
                    size_bytes=result.get("bytes"),
                )
            )

        session.commit()
        session.refresh(application)

    except Exception:
        session.rollback()
        raise

    return {
        "message": "Tender application submitted successfully.",
        "application": {
            "id": application.id,
            "tender_id": application.tender_id,
            "vendor_id": application.vendor_onboarding_id,
            "proposed_total_price": str(
                application.proposed_total_price
            ),
            "delivery_timeline": application.delivery_timeline,
            "proposal": application.proposal,
            "additional_notes": application.additional_notes,
            "status": application.status,
            "submitted_at": application.submitted_at,
        },
    }
