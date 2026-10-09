from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BuyerOnboarding(SQLModel, table=True):
    __tablename__ = "buyer_onboardings"

    id: int | None = Field(default=None, primary_key=True)
    account_id: str = Field(index=True, unique=True)
    organization_name: str
    location: str
    completed_at: datetime = Field(default_factory=utc_now)


class VendorOnboarding(SQLModel, table=True):
    __tablename__ = "vendor_onboardings"

    id: int | None = Field(default=None, primary_key=True)
    account_id: str = Field(index=True, unique=True)
    business_name: str
    location: str
    completed_at: datetime = Field(default_factory=utc_now)


class VendorCategory(SQLModel, table=True):
    __tablename__ = "vendor_categories"

    id: int | None = Field(default=None, primary_key=True)
    vendor_id: int = Field(
        foreign_key="vendor_onboardings.id",
        index=True,
    )
    name: str


class VendorDocument(SQLModel, table=True):
    __tablename__ = "vendor_documents"

    id: int | None = Field(default=None, primary_key=True)
    vendor_id: int = Field(
        foreign_key="vendor_onboardings.id",
        index=True,
    )
    name: str
    url: str
    public_id: str
    file_format: str | None = None
    size_bytes: int | None = None


class VendorGalleryItem(SQLModel, table=True):
    __tablename__ = "vendor_gallery_items"

    id: int | None = Field(default=None, primary_key=True)
    vendor_id: int = Field(
        foreign_key="vendor_onboardings.id",
        index=True,
    )
    url: str
    public_id: str
    file_format: str | None = None
