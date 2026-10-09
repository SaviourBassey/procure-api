from datetime import datetime, timezone

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ApplicationAnalysis(SQLModel, table=True):
    __tablename__ = "application_analyses"

    id: int | None = Field(default=None, primary_key=True)
    application_id: int = Field(
        foreign_key="tender_applications.id",
        index=True,
    )
    tender_id: int = Field(foreign_key="tenders.id", index=True)
    requested_by_account_id: int = Field(index=True)
    provider: str = Field(max_length=80)
    model: str = Field(max_length=120)
    report: dict = Field(sa_column=Column(JSON))
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    created_at: datetime = Field(default_factory=utc_now)
