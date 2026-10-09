from msflib.auth.deps import get_account_dependencies

from app.core.config import settings
from app.db.session import get_keystore, get_session
from app.models import Account

auth_deps = get_account_dependencies(
    AccountModel=Account,
    oauth_token_url="/api/v1/auth/login",
    secret_key=settings.SECRET_KEY,
    session_dep=get_session,
    keystore_dep=get_keystore,
)
