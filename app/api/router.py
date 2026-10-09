from fastapi import APIRouter, Depends, status
from msflib.account.models import AccountCreate, AccountRead
from msflib.account.router import account_router as msflib_account_router
from msflib.auth.router import router as msflib_auth_router
from sqlmodel import Session

from app.actions import account_action, profile_action
from app.core.config import settings
from app.db.session import get_keystore, get_session
from app.dependencies import auth_deps
from app.models import Account, Profile
from app.schemas.auth import SignupRequest

api_router = APIRouter()


@api_router.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}


@api_router.post(
    "/account/signup",
    status_code=status.HTTP_201_CREATED,
    tags=["Accounts"],
)
def signup(
    payload: SignupRequest,
    session: Session = Depends(get_session),
):
    account_data = AccountCreate(
        email=str(payload.email).lower(),
        password=payload.password,
        username=payload.username,
        phone=payload.phone,
        role="user",
        data={"account_type": payload.account_type},
        profile=payload.profile,
    )

    account = account_action.create(session, data=account_data)

    return {
        "id": account.id,
        "email": account.email,
        "username": account.username,
        "account_type": payload.account_type,
        "status": str(account.status),
    }


api_router.include_router(
    msflib_auth_router(
        get_session=get_session,
        get_keystore=get_keystore,
        get_current_account=auth_deps.get_current_account,
        account_type=Account,
        account_read_type=AccountRead,
        settings=settings,
        prefix="",
    ),
    prefix="/auth",
)

api_router.include_router(
    msflib_account_router(
        get_session=get_session,
        get_current_account=auth_deps.get_current_account,
        settings=settings,
        account_type=Account,
        profile_type=Profile,
        account_read_type=AccountRead,
        account_action=account_action,
        profile_action=profile_action,
        prefix="",
    ),
    prefix="/account",
)
