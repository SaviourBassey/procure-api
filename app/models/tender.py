
from datetime import datetime, timezone
from decimal import Decimal

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Tender(SQLModel, table=True):
    __tablename__ = "tenders"

    id: int | None = Field(default=None, primary_key=True)
    buyer_onboarding_id: int = Field(
        foreign_key="buyer_onboardings.id",
        index=True,
    )

    title: str = Field(max_length=200)
    category: str = Field(max_length=100)
    procurement_type: str = Field(max_length=100)
    maximum_budget: Decimal = Field(
        gt=0,
        max_digits=14,
        decimal_places=2,
    )
    submission_deadline: datetime
    delivery_location: str = Field(max_length=300)
    optional_description: str | None = None
    optional_notes: str | None = None

    status: str = Field(default="open", max_length=30)
    created_at: datetime = Field(default_factory=utc_now)


class TenderItem(SQLModel, table=True):
    __tablename__ = "tender_items"

    id: int | None = Field(default=None, primary_key=True)
    tender_id: int = Field(foreign_key="tenders.id", index=True)

    item: str = Field(max_length=200)
    quantity: Decimal = Field(
        gt=0,
        max_digits=14,
        decimal_places=3,
    )
    unit: str = Field(max_length=50)


class TenderProductRequirement(SQLModel, table=True):
    __tablename__ = "tender_product_requirements"

    id: int | None = Field(default=None, primary_key=True)
    tender_id: int = Field(foreign_key="tenders.id", index=True)

    requirement_name: str = Field(max_length=200)
    value: str = Field(max_length=2000)


class TenderRequiredDocument(SQLModel, table=True):
    __tablename__ = "tender_required_documents"

    id: int | None = Field(default=None, primary_key=True)
    tender_id: int = Field(foreign_key="tenders.id", index=True)

    name: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=1000)
