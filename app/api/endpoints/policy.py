from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db.session import get_session
from app.dependencies import auth_deps
from app.models import Account
from app.services.procurement_policy import resolve_procurement

policy_router = APIRouter()


@policy_router.get("", tags=["Procurement policy"])
def get_procurement_policy(
    current_account: Account = Depends(auth_deps.get_current_account),
    session: Session = Depends(get_session),
):
    resolved, trace, scope = resolve_procurement(session, current_account)
    winning = {
        key: getattr(layer, "value", str(layer))
        for key, layer in trace.winning_layers.items()
    }
    return {
        "currency": resolved.CURRENCY,
        "analysis_model": resolved.ANALYSIS_MODEL,
        "scope": scope,
        "winning_layers": winning,
        "rejected_overrides": [
            {"key": item.key, "reason": item.reason} for item in trace.rejected_overrides
        ],
    }
