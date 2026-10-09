
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
