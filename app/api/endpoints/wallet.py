from decimal import Decimal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db.session import get_session
from app.dependencies import auth_deps
from app.models import Account, WalletEntry, Withdrawal
from app.services.escrow import get_or_create_wallet, money, request_withdrawal

wallet_router = APIRouter()


class WithdrawalRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    bank_name: str = Field(min_length=2, max_length=120)
    account_name: str = Field(min_length=2, max_length=200)
    account_number: str = Field(min_length=10, max_length=20)


def _withdrawal_payload(row: Withdrawal) -> dict:
    return {
        "id": row.id,
        "amount": str(money(row.amount)),
        "currency": row.currency,
        "status": row.status,
        "bank_name": row.bank_name,
        "account_name": row.account_name,
        "account_number": row.account_number,
        "created_at": row.created_at,
    }


@wallet_router.get("", tags=["Wallet"])
def get_wallet(
    current_account: Account = Depends(auth_deps.get_current_account),
    session: Session = Depends(get_session),
):
    wallet = get_or_create_wallet(session, current_account.id)
    session.commit()
    entries = list(
        session.exec(
            select(WalletEntry)
            .where(WalletEntry.wallet_id == wallet.id)
            .order_by(WalletEntry.created_at.desc())
            .limit(50)
        ).all()
    )
    return {
        "account_id": wallet.account_id,
        "currency": wallet.currency,
        "available_balance": str(money(wallet.available_balance)),
        "entries": [
            {
                "id": entry.id,
                "direction": entry.direction,
                "amount": str(money(entry.amount)),
                "balance_after": str(money(entry.balance_after)),
                "entry_type": entry.entry_type,
                "reference_type": entry.reference_type,
                "reference_id": entry.reference_id,
                "note": entry.note,
                "created_at": entry.created_at,
            }
            for entry in entries
        ],
    }


@wallet_router.post(
    "/withdrawals",
    status_code=status.HTTP_201_CREATED,
    tags=["Wallet"],
)
def create_withdrawal(
    payload: WithdrawalRequest,
    current_account: Account = Depends(auth_deps.get_current_account),
    session: Session = Depends(get_session),
):
    withdrawal = request_withdrawal(
        session,
        account=current_account,
        amount=payload.amount,
        bank_name=payload.bank_name,
        account_name=payload.account_name,
        account_number=payload.account_number,
    )
    return {
        "message": "Withdrawal requested. Payout stays pending until it is sent to your bank.",
        "withdrawal": _withdrawal_payload(withdrawal),
    }


@wallet_router.get("/withdrawals", tags=["Wallet"])
def list_withdrawals(
    current_account: Account = Depends(auth_deps.get_current_account),
    session: Session = Depends(get_session),
):
    rows = list(
        session.exec(
            select(Withdrawal)
            .where(Withdrawal.account_id == current_account.id)
            .order_by(Withdrawal.created_at.desc())
        ).all()
    )
    return {
        "count": len(rows),
        "withdrawals": [_withdrawal_payload(row) for row in rows],
    }
