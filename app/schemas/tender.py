
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TenderItemCreate(BaseModel):
    item: str = Field(min_length=1, max_length=200)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit: str = Field(min_length=1, max_length=50)


class ProductRequirementCreate(BaseModel):
    requirement_name: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=2000)


class RequiredDocumentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)


class TenderCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    procurement_type: str = Field(min_length=1, max_length=100)
    maximum_budget: Decimal = Field(
        gt=0,
        max_digits=14,
        decimal_places=2,
    )
    submission_deadline: datetime
    delivery_location: str = Field(min_length=2, max_length=300)
    optional_description: str | None = Field(
        default=None,
        max_length=5000,
    )
    items: list[TenderItemCreate] = Field(min_length=1, max_length=100)
    product_requirements: list[ProductRequirementCreate] = Field(
        default_factory=list,
        max_length=100,
    )
    required_documents: list[RequiredDocumentCreate] = Field(
        default_factory=list,
        max_length=50,
    )
    optional_notes: str | None = Field(default=None, max_length=5000)

    @field_validator("submission_deadline")
    @classmethod
    def validate_submission_deadline(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "submission_deadline must include a timezone, such as Z or +01:00."
            )

        if value <= datetime.now(timezone.utc):
            raise ValueError("submission_deadline must be in the future.")

        return value


class TenderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: str
    procurement_type: str
    maximum_budget: Decimal
    submission_deadline: datetime
    delivery_location: str
    optional_description: str | None
    optional_notes: str | None
    status: str
    created_at: datetime
