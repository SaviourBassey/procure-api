import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import (
    Account,
    ProcurementOrder,
    Tender,
    TenderApplication,
    Wallet,
    WalletEntry,
    Withdrawal,
)
from app.models.commerce import utc_now
from app.services.notify import notify_accounts

logger = logging.getLogger(__name__)

ESCROW_EVENT_KEY = "escrow-fund"


def money(value: Decimal | str | float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def serialize_order(
    order: ProcurementOrder,
    tender: Tender | None = None,
    vendor_name: str | None = None,
) -> dict:
    return {
        "id": order.id,
        "application_id": order.application_id,
        "tender_id": order.tender_id,
        "tender_title": tender.title if tender else None,
        "buyer_account_id": order.buyer_account_id,
        "vendor_account_id": order.vendor_account_id,
        "vendor_business_name": vendor_name,
        "amount": str(money(order.amount)),
        "currency": order.currency,
        "status": order.status,
        "escrow_status": order.escrow_status,
        "payment_id": order.payment_id,
        "payment_reference": order.payment_reference,
        "shipping_note": order.shipping_note,
        "tracking_reference": order.tracking_reference,
        "funded_at": order.funded_at,
        "shipped_at": order.shipped_at,
        "received_at": order.received_at,
        "created_at": order.created_at,
    }


def get_or_create_wallet(session: Session, account_id: int) -> Wallet:
    wallet = session.exec(
        select(Wallet).where(Wallet.account_id == account_id)
    ).first()
    if wallet is not None:
        return wallet

    wallet = Wallet(account_id=account_id, available_balance=Decimal("0.00"))
    session.add(wallet)
    session.flush()
    return wallet


def fund_escrow(session: Session, order_id: int) -> ProcurementOrder:
    """Move a paid order into escrow and tell the vendor they can ship.

    Idempotent once the hold is in place, so a repeated payment verification
    does not send a second approval notice.
    """
    order = session.get(ProcurementOrder, order_id)
    if order is None:
        raise RuntimeError(f"Escrow order {order_id} was not found.")

    if order.escrow_status in {"held", "released"}:
        return order

    vendor = session.get(Account, order.vendor_account_id)
    buyer = session.get(Account, order.buyer_account_id)
    if vendor is None:
        raise RuntimeError("Vendor account for this order was not found.")

    tender = session.get(Tender, order.tender_id)
    application = session.get(TenderApplication, order.application_id)

    order.escrow_status = "held"
    order.status = "ready_to_ship"
    order.funded_at = datetime.now(timezone.utc)
    session.add(order)

    if application is not None and application.status != "accepted":
        application.status = "accepted"
        session.add(application)

    if tender is not None and tender.status in {"open", "active"}:
        tender.status = "awarded"
        session.add(tender)

    title = tender.title if tender else f"tender {order.tender_id}"
    notify_accounts(
        session,
        recipients=[vendor],
        sender=buyer,
        title="You are approved to ship",
        message=(
            f"Your application for \"{title}\" has been accepted. "
            f"{money(order.amount)} {order.currency} is held in escrow. "
            "Ship the order, then mark it shipped in Procure."
        ),
    )
    return order


def release_escrow(session: Session, order: ProcurementOrder) -> Wallet:
    if order.escrow_status == "released":
        raise HTTPException(
            status_code=409,
            detail="Escrow for this order has already been released.",
        )
    if order.escrow_status != "held":
        raise HTTPException(
            status_code=409,
            detail="Escrow is not funded yet. The buyer must complete payment first.",
        )
    if order.status != "shipped":
        raise HTTPException(
            status_code=409,
            detail="The vendor must mark the order shipped before you confirm receipt.",
        )

    wallet = get_or_create_wallet(session, order.vendor_account_id)
    amount = money(order.amount)
    balance = money(wallet.available_balance) + amount
    wallet.available_balance = balance
    wallet.updated_at = utc_now()
    session.add(wallet)

    session.add(
        WalletEntry(
            wallet_id=wallet.id,
            account_id=order.vendor_account_id,
            direction="credit",
            amount=amount,
            balance_after=balance,
            entry_type="escrow_release",
            reference_type="procurement_order",
            reference_id=order.id,
            note="Buyer confirmed receipt. Escrow released to the vendor wallet.",
        )
    )

    order.escrow_status = "released"
    order.status = "completed"
    order.received_at = utc_now()
    session.add(order)
    session.commit()
    session.refresh(wallet)
    session.refresh(order)

    vendor = session.get(Account, order.vendor_account_id)
    buyer = session.get(Account, order.buyer_account_id)
    tender = session.get(Tender, order.tender_id)
    title = tender.title if tender else f"tender {order.tender_id}"
    if vendor is not None:
        notify_accounts(
            session,
            recipients=[vendor],
            sender=buyer,
            title="Escrow released to your wallet",
            message=(
                f"The buyer confirmed receipt for \"{title}\". "
                f"{amount} {order.currency} is now available in your wallet."
            ),
        )
    return wallet


def request_withdrawal(
    session: Session,
    *,
    account: Account,
    amount: Decimal,
    bank_name: str,
    account_name: str,
    account_number: str,
) -> Withdrawal:
    wallet = get_or_create_wallet(session, account.id)
    available = money(wallet.available_balance)
    debit = money(amount)
    if debit > available:
        raise HTTPException(
            status_code=422,
            detail=f"Withdrawal exceeds the available balance of {available} {wallet.currency}.",
        )

    balance = available - debit
    wallet.available_balance = balance
    wallet.updated_at = utc_now()
    session.add(wallet)
    session.flush()

    withdrawal = Withdrawal(
        wallet_id=wallet.id,
        account_id=account.id,
        amount=debit,
        currency=wallet.currency,
        status="pending",
        bank_name=bank_name.strip(),
        account_name=account_name.strip(),
        account_number=account_number.strip(),
    )
    session.add(withdrawal)
    session.flush()
    session.add(
        WalletEntry(
            wallet_id=wallet.id,
            account_id=account.id,
            direction="debit",
            amount=debit,
            balance_after=balance,
            entry_type="withdrawal",
            reference_type="withdrawal",
            reference_id=withdrawal.id,
            note="Withdrawal requested. Funds leave the available balance while payout is pending.",
        )
    )
    session.commit()
    session.refresh(withdrawal)

    notify_accounts(
        session,
        recipients=[account],
        title="Withdrawal requested",
        message=(
            f"Your withdrawal of {debit} {wallet.currency} to {withdrawal.bank_name} "
            f"account {withdrawal.account_number} is pending payout."
        ),
    )
    return withdrawal
