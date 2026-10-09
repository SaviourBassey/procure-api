from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import Account, BuyerOnboarding, VendorOnboarding


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_account_type(account: Account) -> str | None:
    data = getattr(account, "data", None) or {}

    if hasattr(data, "model_dump"):
        data = data.model_dump()

    if isinstance(data, dict):
        value = data.get("account_type")
        return str(value).lower() if value else None

    return None


def require_buyer(account: Account, session: Session) -> BuyerOnboarding:
    if get_account_type(account) != "buyer":
        raise HTTPException(
            status_code=403,
            detail="Only buyer accounts can access this endpoint.",
        )

    buyer = session.exec(
        select(BuyerOnboarding).where(
            BuyerOnboarding.account_id == str(account.id)
        )
    ).first()

    if buyer is None:
        raise HTTPException(
            status_code=403,
            detail="Complete buyer onboarding first.",
        )

    return buyer


def require_vendor(account: Account, session: Session) -> VendorOnboarding:
    if get_account_type(account) != "vendor":
        raise HTTPException(
            status_code=403,
            detail="Only vendor accounts can access this endpoint.",
        )

    vendor = session.exec(
        select(VendorOnboarding).where(
            VendorOnboarding.account_id == str(account.id)
        )
    ).first()

    if vendor is None:
        raise HTTPException(
            status_code=403,
            detail="Complete vendor onboarding first.",
        )

    return vendor
