
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenderApplication(SQLModel, table=True):
    __tablename__ = "tender_applications"
    __table_args__ = (
        UniqueConstraint(
            "tender_id",
            "vendor_onboarding_id",
            name="uq_tender_vendor_application",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    tender_id: int = Field(
        foreign_key="tenders.id",
        index=True,
    )
    vendor_onboarding_id: int = Field(
        foreign_key="vendor_onboardings.id",
        index=True,
    )
    proposed_total_price: Decimal = Field(
        gt=0,
        max_digits=14,
        decimal_places=2,
    )
    delivery_timeline: str = Field(max_length=200)
    proposal: str | None = None
    additional_notes: str | None = None
    status: str = Field(default="submitted", max_length=30)
    submitted_at: datetime = Field(default_factory=utc_now)


class ApplicationItemQuote(SQLModel, table=True):
    __tablename__ = "application_item_quotes"

    id: int | None = Field(default=None, primary_key=True)
    application_id: int = Field(
        foreign_key="tender_applications.id",
        index=True,
    )
    tender_item_id: int = Field(
        foreign_key="tender_items.id",
        index=True,
    )
    unit_price: Decimal = Field(
        gt=0,
        max_digits=14,
        decimal_places=2,
    )
    total_price: Decimal = Field(
        gt=0,
        max_digits=16,
        decimal_places=2,
    )


class ApplicationRequirementResponse(SQLModel, table=True):
    __tablename__ = "application_requirement_responses"

    id: int | None = Field(default=None, primary_key=True)
    application_id: int = Field(
        foreign_key="tender_applications.id",
        index=True,
    )
    requirement_id: int = Field(
        foreign_key="tender_product_requirements.id",
        index=True,
    )
    response: str = Field(max_length=3000)


class ApplicationDocument(SQLModel, table=True):
    __tablename__ = "application_documents"

    id: int | None = Field(default=None, primary_key=True)
    application_id: int = Field(
        foreign_key="tender_applications.id",
        index=True,
    )
    name: str = Field(max_length=200)
    url: str
    public_id: str
    file_format: str | None = None
    size_bytes: int | None = None
