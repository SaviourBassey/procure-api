
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

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
from app.schemas.tender import TenderCreate


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
