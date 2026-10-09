
from decimal import Decimal

from pydantic import BaseModel, Field


class ItemQuoteCreate(BaseModel):
    tender_item_id: int
    unit_price: Decimal = Field(
        gt=0,
        max_digits=14,
        decimal_places=2,
    )


class RequirementResponseCreate(BaseModel):
    requirement_id: int
    response: str = Field(min_length=1, max_length=3000)


class TenderApplicationCreate(BaseModel):
    delivery_timeline: str = Field(
        min_length=1,
        max_length=200,
    )
    item_quotes: list[ItemQuoteCreate] = Field(
        min_length=1,
        max_length=100,
    )
    proposal: str | None = Field(
        default=None,
        max_length=10000,
    )
    requirement_responses: list[
        RequirementResponseCreate
    ] = Field(default_factory=list, max_length=100)
    additional_notes: str | None = Field(
        default=None,
        max_length=5000,
    )
