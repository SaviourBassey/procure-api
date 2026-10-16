from msflib.auth.deps import get_account_dependencies, get_user_dependencies
from msflib.auth.resolvers import PathParameterResolver
from msflib.tenancy.deps import get_tenant_dependencies
from msflib.workspaces.models.user import User
from msflib.workspaces.models.workspace import Workspace

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

tenant_deps = get_tenant_dependencies(
    session_dep=get_session,
    settings=settings.scope("TENANCY"),
)

user_deps = get_user_dependencies(
    UserModel=User,
    WorkspaceModel=Workspace,
    session_dep=get_session,
    account_dependencies=auth_deps,
    workspace_resolver=PathParameterResolver(),
)
