from datetime import datetime, timezone
from decimal import Decimal

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProcurementOrder(SQLModel, table=True):
    __tablename__ = "procurement_orders"

    id: int | None = Field(default=None, primary_key=True)
    application_id: int = Field(
        foreign_key="tender_applications.id",
        unique=True,
        index=True,
    )
    tender_id: int = Field(foreign_key="tenders.id", index=True)
    buyer_account_id: int = Field(index=True)
    vendor_account_id: int = Field(index=True)
    buyer_onboarding_id: int = Field(foreign_key="buyer_onboardings.id")
    vendor_onboarding_id: int = Field(foreign_key="vendor_onboardings.id")
    amount: Decimal = Field(max_digits=16, decimal_places=2)
    currency: str = Field(default="NGN", max_length=8)
    # awaiting_payment, ready_to_ship, shipped, completed
    status: str = Field(default="awaiting_payment", max_length=30)
    # pending_payment, held, released
    escrow_status: str = Field(default="pending_payment", max_length=30)
    payment_id: int | None = Field(default=None, index=True)
    payment_reference: str | None = Field(default=None, index=True)
    shipping_note: str | None = None
    tracking_reference: str | None = Field(default=None, max_length=200)
    funded_at: datetime | None = None
    shipped_at: datetime | None = None
    received_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Wallet(SQLModel, table=True):
    __tablename__ = "wallets"

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(unique=True, index=True)
    currency: str = Field(default="NGN", max_length=8)
    available_balance: Decimal = Field(
        default=Decimal("0.00"),
        max_digits=16,
        decimal_places=2,
    )
    updated_at: datetime = Field(default_factory=utc_now)


class WalletEntry(SQLModel, table=True):
    __tablename__ = "wallet_entries"

    id: int | None = Field(default=None, primary_key=True)
    wallet_id: int = Field(foreign_key="wallets.id", index=True)
    account_id: int = Field(index=True)
    direction: str = Field(max_length=10)  # credit or debit
    amount: Decimal = Field(max_digits=16, decimal_places=2)
    balance_after: Decimal = Field(max_digits=16, decimal_places=2)
    entry_type: str = Field(max_length=40)
    reference_type: str = Field(max_length=40)
    reference_id: int
    note: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Withdrawal(SQLModel, table=True):
    __tablename__ = "withdrawals"

    id: int | None = Field(default=None, primary_key=True)
    wallet_id: int = Field(foreign_key="wallets.id", index=True)
    account_id: int = Field(index=True)
    amount: Decimal = Field(max_digits=16, decimal_places=2)
    currency: str = Field(default="NGN", max_length=8)
    status: str = Field(default="pending", max_length=20)
    bank_name: str = Field(max_length=120)
    account_name: str = Field(max_length=200)
    account_number: str = Field(max_length=20)
    created_at: datetime = Field(default_factory=utc_now)
