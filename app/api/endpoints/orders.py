
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db.session import get_session
from app.dependencies import auth_deps
from app.models import (
    Account,
    ProcurementOrder,
    Tender,
    TenderApplication,
    VendorOnboarding,
)
from app.services.access import require_buyer, require_vendor
from app.services.escrow import (
    ESCROW_EVENT_KEY,
    money,
    release_escrow,
    serialize_order,
)
from app.services.notify import notify_accounts

acceptance_router = APIRouter()
order_router = APIRouter()


class AcceptApplicationRequest(BaseModel):
    callback_url: str | None = None


class ShipRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    tracking_reference: str | None = Field(default=None, max_length=200)


class ReceiveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


def _vendor_name(session: Session, vendor_id: int) -> str | None:
    vendor = session.get(VendorOnboarding, vendor_id)
    return vendor.business_name if vendor else None


def _order_payload(session: Session, order: ProcurementOrder) -> dict:
    tender = session.get(Tender, order.tender_id)
    return serialize_order(
        order,
        tender=tender,
        vendor_name=_vendor_name(session, order.vendor_onboarding_id),
    )


def _get_order_for_account(
    order_id: int,
    account: Account,
    session: Session,
) -> ProcurementOrder:
    order = session.get(ProcurementOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found.")
    if account.id not in {order.buyer_account_id, order.vendor_account_id}:
        raise HTTPException(status_code=404, detail="Order not found.")
    return order


@acceptance_router.post(
    "/{application_id}/accept",
    status_code=status.HTTP_201_CREATED,
    tags=["Escrow"],
)
async def accept_application(
    application_id: int,
    payload: AcceptApplicationRequest | None = None,
    current_account: Account = Depends(auth_deps.get_current_account),
    session: Session = Depends(get_session),
):
    """Accept one application and start a Paystack payment into escrow.

    The vendor is told to ship only after Paystack verification funds the hold.
    """
    from msflib.payments.models import Payment, PaymentData, PaymentGateway
    from msflib.payments.service.error import PaymentError
    from msflib.payments.service.processor import process_payment

    from app.core.config import settings

    buyer = require_buyer(current_account, session)
    application = session.get(TenderApplication, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")

    tender = session.get(Tender, application.tender_id)
    if tender is None or tender.buyer_onboarding_id != buyer.id:
        raise HTTPException(status_code=404, detail="Application not found.")

    if tender.status == "awarded" and application.status != "accepted":
        raise HTTPException(
            status_code=409,
            detail="This tender has already been awarded.",
        )

    if application.status not in {"submitted", "accepted"}:
        raise HTTPException(
            status_code=409,
            detail=f"This application cannot be accepted from status '{application.status}'.",
        )

    existing = session.exec(
        select(ProcurementOrder).where(
            ProcurementOrder.application_id == application.id
        )
    ).first()
    if existing is not None:
        if existing.escrow_status in {"held", "released"}:
            raise HTTPException(
                status_code=409,
                detail="Payment for this application is already in escrow.",
            )
        payment = None
        if existing.payment_reference:
            payment = session.exec(
                select(Payment).where(Payment.reference == existing.payment_reference)
            ).first()
        return {
            "message": "Finish the existing Paystack payment to fund escrow.",
            "order": _order_payload(session, existing),
            "payment": _payment_payload(payment, existing),
            "next_step": (
                "Open authorization_url, pay, then call "
                "GET /api/v1/payments/verify/{reference}."
            ),
        }

    vendor = session.get(VendorOnboarding, application.vendor_onboarding_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor profile was not found.")

    amount = money(application.proposed_total_price)
    order = ProcurementOrder(
        application_id=application.id,
        tender_id=tender.id,
        buyer_account_id=current_account.id,
        vendor_account_id=int(vendor.account_id),
        buyer_onboarding_id=buyer.id,
        vendor_onboarding_id=vendor.id,
        amount=amount,
        currency="NGN",
        status="awaiting_payment",
        escrow_status="pending_payment",
    )

    paystack_key = str(
        getattr(settings.scope("PAYMENTS"), "PAYSTACK_SECRET_KEY", "") or ""
    ).strip()
    if not paystack_key:
        raise HTTPException(
            status_code=503,
            detail="Paystack is not configured. Set PAYSTACK_SECRET_KEY and try again.",
        )

    callback_url = payload.callback_url if payload else None
    try:
        session.add(order)
        session.flush()
        payment = await process_payment(
            session=session,
            payment_data=PaymentData(
                email=current_account.email,
                amount=float(f"{amount:.2f}"),
                description=f"Escrow for {tender.title}",
                gateway=PaymentGateway.paystack,
                callback_url=callback_url,
            ),
            account=current_account,
            settings=settings,
            queue_event_key=ESCROW_EVENT_KEY,
            queue_data={"order_id": order.id, "application_id": application.id},
        )
    except PaymentError as exc:
        session.rollback()
        raise HTTPException(
            status_code=502,
            detail=(
                "Paystack could not start this payment. "
                "Check PAYSTACK_SECRET_KEY and try again."
            ),
        ) from exc
    except Exception:
        session.rollback()
        raise

    order = session.get(ProcurementOrder, order.id)
    if order is None:
        raise HTTPException(
            status_code=500,
            detail="The escrow order was not saved.",
        )
    order.payment_id = payment.id
    order.payment_reference = payment.reference
    session.add(order)
    session.commit()
    session.refresh(order)

    return {
        "message": "Application accepted. Complete Paystack payment to fund escrow.",
        "order": _order_payload(session, order),
        "payment": _payment_payload(payment, order),
        "next_step": (
            "Open authorization_url, pay, then call "
            "GET /api/v1/payments/verify/{reference}. "
            "The vendor is notified only after that verification."
        ),
    }


def _payment_payload(payment, order: ProcurementOrder) -> dict:
    if payment is None:
        return {
            "reference": order.payment_reference,
            "amount": str(money(order.amount)),
            "currency": order.currency,
            "status": "unverified",
        }
    status_value = payment.status
    if hasattr(status_value, "value"):
        status_value = status_value.value
    return {
        "id": payment.id,
        "reference": payment.reference,
        "authorization_url": payment.authorization_url,
        "access_code": payment.access_code,
        "amount": str(money(order.amount)),
        "currency": order.currency,
        "status": str(status_value),
    }


@order_router.get("", tags=["Orders"])
def list_orders(
    current_account: Account = Depends(auth_deps.get_current_account),
    session: Session = Depends(get_session),
):
    orders = list(
        session.exec(
            select(ProcurementOrder)
            .where(
                (ProcurementOrder.buyer_account_id == current_account.id)
                | (ProcurementOrder.vendor_account_id == current_account.id)
            )
            .order_by(ProcurementOrder.created_at.desc())
        ).all()
    )
    return {
        "count": len(orders),
        "orders": [_order_payload(session, order) for order in orders],
    }


@order_router.get("/{order_id}", tags=["Orders"])
def get_order(
    order_id: int,
    current_account: Account = Depends(auth_deps.get_current_account),
    session: Session = Depends(get_session),
):
    order = _get_order_for_account(order_id, current_account, session)
    return {"order": _order_payload(session, order)}


@order_router.post("/{order_id}/ship", tags=["Orders"])
def mark_shipped(
    order_id: int,
    payload: ShipRequest | None = None,
    current_account: Account = Depends(auth_deps.get_current_account),
    session: Session = Depends(get_session),
):
    require_vendor(current_account, session)
    order = _get_order_for_account(order_id, current_account, session)
    if order.vendor_account_id != current_account.id:
        raise HTTPException(status_code=403, detail="Only the awarded vendor can ship this order.")
    if order.status == "shipped":
        return {"message": "This order is already marked shipped.", "order": _order_payload(session, order)}
    if order.status != "ready_to_ship" or order.escrow_status != "held":
        raise HTTPException(
            status_code=409,
            detail="You can ship after the buyer's escrow payment has been verified.",
        )

    body = payload or ShipRequest()
    order.status = "shipped"
    order.shipping_note = body.note.strip() if body.note else None
    order.tracking_reference = (
        body.tracking_reference.strip() if body.tracking_reference else None
    )
    from app.models.commerce import utc_now

    order.shipped_at = utc_now()
    session.add(order)
    session.commit()
    session.refresh(order)

    buyer = session.get(Account, order.buyer_account_id)
    tender = session.get(Tender, order.tender_id)
    title = tender.title if tender else f"order {order.id}"
    tracking = f" Tracking reference: {order.tracking_reference}." if order.tracking_reference else ""
    notified = False
    if buyer is not None:
        notified = notify_accounts(
            session,
            recipients=[buyer],
            sender=current_account,
            title="Your order has shipped",
            message=(
                f"The vendor marked \"{title}\" as shipped.{tracking} "
                "Confirm receipt when the goods arrive to release escrow."
            ),
        )

    return {
        "message": "Shipment recorded. The buyer has been notified.",
        "notification_sent": notified,
        "order": _order_payload(session, order),
    }


@order_router.post("/{order_id}/receive", tags=["Orders"])
def mark_received(
    order_id: int,
    payload: ReceiveRequest | None = None,
    current_account: Account = Depends(auth_deps.get_current_account),
    session: Session = Depends(get_session),
):
    buyer = require_buyer(current_account, session)
    order = _get_order_for_account(order_id, current_account, session)
    if order.buyer_account_id != current_account.id:
        raise HTTPException(
            status_code=403,
            detail="Only the buyer can confirm receipt.",
        )
    if order.buyer_onboarding_id != buyer.id:
        raise HTTPException(status_code=404, detail="Order not found.")

    # Receipt is what releases the held Paystack funds into the vendor wallet.
    _ = payload
    wallet = release_escrow(session, order)
    session.refresh(order)
    return {
        "message": "Receipt confirmed. Escrow has been released to the vendor wallet.",
        "order": _order_payload(session, order),
        "vendor_wallet": {
            "account_id": wallet.account_id,
            "available_balance": str(money(wallet.available_balance)),
            "currency": wallet.currency,
        },
    }
