"""Mount the msflib module routers the host app does not already own."""

from types import SimpleNamespace

from fastapi import APIRouter, Depends
from msflib.account.models import AccountRead, AccountRole
from msflib.account.router import account_admin_router, profile_router
from msflib.ai_api.router import router as create_ai_router
from msflib.ai_core.router.ai_provider import admin_router as create_ai_provider_admin_router
from msflib.ai_core.router.vector_store import admin_router as create_vector_store_admin_router
from msflib.conversation.router import router as create_conversation_router
from msflib.documents.router import router as create_documents_router
from msflib.drivelink.router import router as create_drivelink_router
from msflib.ingestion.router import router as create_ingestion_router
from msflib.knowledge.integrations.ai_api import resolve_knowledge_tool_registries
from msflib.notifications.router import admin_account_notification_router
from msflib.workspace_config.router import router as create_workspace_config_router
from msflib.workspace_notifications.router import (
    admin_user_notification_router,
    user_notification_router,
)
from msflib.workspaces.models.user import User
from msflib.workspaces.models.workspace import Workspace
from msflib.workspaces.router import (
    router as create_workspace_router,
)
from msflib.workspaces.router import (
    user_me_router,
    user_workspace_router,
)

from app.actions import account_action, profile_action
from app.core.config import settings
from app.core.knowledge import get_knowledge_engine
from app.db.session import get_session
from app.dependencies import auth_deps, tenant_deps, user_deps
from app.models import Account, Profile


def _workspace_from_account(account=Depends(auth_deps.get_current_account)):
    if account is None or account.current_workspace_id is None:
        return None
    return SimpleNamespace(id=account.current_workspace_id)


def library_router() -> APIRouter:
    router = APIRouter()

    router.include_router(
        account_admin_router(
            get_session=get_session,
            role_check=auth_deps.RoleCheck,
            settings=settings,
            account_type=Account,
            profile_type=Profile,
            account_read_type=AccountRead,
            account_action=account_action,
            profile_action=profile_action,
            prefix="",
            tags=["admin_accounts"],
        ),
        prefix="/admin/accounts",
    )
    router.include_router(
        profile_router(
            get_session=get_session,
            get_current_account=auth_deps.get_current_account,
            get_current_active_account=auth_deps.get_current_active_account,
            settings=settings,
            profile_type=Profile,
            account_type=Account,
            profile_action=profile_action,
            account_action=account_action,
            prefix="",
            tags=["profiles"],
        ),
        prefix="/profiles",
    )
    router.include_router(
        admin_account_notification_router(
            get_session=get_session,
            get_current_account=auth_deps.get_current_account,
            role_check=auth_deps.RoleCheck,
            settings=settings,
            account_action=account_action,
            prefix="",
            tags=["admin_notifications"],
        ),
        prefix="/admin/notifications",
    )
    router.include_router(
        create_workspace_router(
            get_session=get_session,
            get_current_account=auth_deps.get_current_account,
            get_current_account_or_none=auth_deps.get_current_account_or_none,
            role_check=auth_deps.RoleCheck,
            settings=settings,
            account_type=Account,
            workspace_type=Workspace,
            user_type=User,
            get_current_tenant=tenant_deps.get_current_tenant,
            prefix="",
            tags=["workspaces"],
        ),
        prefix="/workspaces",
    )
    router.include_router(
        user_workspace_router(
            get_session=get_session,
            get_current_account=auth_deps.get_current_account,
            get_current_active_account=auth_deps.get_current_active_account,
            settings=settings,
            workspace_type=Workspace,
            user_type=User,
            prefix="",
            tags=["workspace_users"],
        ),
        prefix="/users",
    )
    router.include_router(
        user_me_router(
            get_session=get_session,
            get_current_account=auth_deps.get_current_account,
            get_current_active_account=auth_deps.get_current_active_account,
            get_current_workspace=user_deps.get_current_workspace,
            user_type=User,
            prefix="",
            tags=["workspace_me"],
        ),
        prefix="/{workspace_slug}/users",
    )
    router.include_router(
        create_workspace_config_router(
            get_session=get_session,
            settings=settings,
            get_current_workspace=user_deps.get_current_workspace,
            get_current_workspace_anonymous=user_deps.get_current_workspace_anonymous,
            get_current_active_user=user_deps.get_current_active_user,
            workspace_role_check=user_deps.WorkspaceRoleCheck,
            prefix="",
            tags=["workspace_config"],
        ),
        prefix="/{workspace_slug}/config",
    )
    router.include_router(
        user_notification_router(
            get_session=get_session,
            get_current_user=user_deps.get_current_user,
            get_current_workspace=user_deps.get_current_workspace,
            prefix="",
            tags=["workspace_notifications"],
        ),
        prefix="/{workspace_slug}/workspace-notifications",
    )
    router.include_router(
        admin_user_notification_router(
            get_session=get_session,
            get_current_user=user_deps.get_current_user,
            get_current_workspace=user_deps.get_current_workspace,
            admin_role_check=user_deps.WorkspaceRoleCheck(["owner", "admin"]),
            settings=settings,
            prefix="",
            tags=["workspace_notifications_admin"],
        ),
        prefix="/{workspace_slug}/workspace-notifications/admin",
    )
    router.include_router(
        create_documents_router(
            get_session=get_session,
            settings=settings,
            get_current_account=auth_deps.get_current_account,
            get_current_workspace=_workspace_from_account,
            get_current_tenant=tenant_deps.get_current_tenant,
            prefix="",
            tags=["documents"],
        ),
        prefix="/documents",
    )
    router.include_router(
        create_drivelink_router(
            get_session=get_session,
            get_current_account=auth_deps.get_current_account,
            settings=settings,
            get_current_workspace=_workspace_from_account,
            prefix="",
            tags=["drivelink"],
        ),
        prefix="/drivelink",
    )
    router.include_router(
        create_ingestion_router(
            get_session=get_session,
            settings=settings,
            mutation_role_check=auth_deps.RoleCheck(roles=[AccountRole.admin, AccountRole.root]),
            get_current_workspace=_workspace_from_account,
            get_current_tenant=tenant_deps.get_current_tenant,
            prefix="",
            tags=["ingestion"],
        ),
        prefix="/ingestion",
    )
    router.include_router(
        create_conversation_router(
            get_session=get_session,
            get_current_account=auth_deps.get_current_account,
            settings=settings,
            get_current_workspace=_workspace_from_account,
            get_current_tenant=tenant_deps.get_current_tenant,
            prefix="",
            tags=["conversation"],
        ),
        prefix="/conversation",
    )
    router.include_router(
        create_ai_router(
            get_session=get_session,
            get_current_account=auth_deps.get_current_account,
            get_current_workspace=_workspace_from_account,
            get_current_tenant=tenant_deps.get_current_tenant,
            settings=settings,
            get_tool_registries=resolve_knowledge_tool_registries(get_knowledge_engine),
            system_prompt=(
                "You answer procurement questions from indexed tender and application "
                "documents. Say when the indexed evidence does not support a claim."
            ),
            checkpoint_backend="memory",
            memory_backend="memory",
            prefix="",
            tags=["ai"],
        ),
        prefix="/ai",
    )
    router.include_router(
        create_ai_provider_admin_router(
            get_session=get_session,
            settings=settings,
            get_current_active_superuser=auth_deps.get_current_active_superuser,
            get_current_tenant=tenant_deps.get_current_tenant,
            prefix="",
            tags=["ai_providers_admin"],
        ),
        prefix="/ai/admin/providers",
    )
    router.include_router(
        create_vector_store_admin_router(
            get_session=get_session,
            settings=settings,
            get_current_active_superuser=auth_deps.get_current_active_superuser,
            get_current_tenant=tenant_deps.get_current_tenant,
            prefix="",
            tags=["ai_vector_stores_admin"],
        ),
        prefix="/ai/admin/vector-stores",
    )
    return router
