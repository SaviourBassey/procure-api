"""Tenant and workspace provisioning through the msflib tenancy and workspaces modules."""

import logging
import re

from msflib.tenancy.models.tenant import Tenant
from msflib.tenancy.resolver import resolve_default_tenant_id
from msflib.workspace_config.models.config import ConfigScopeType
from msflib.workspace_config.service import ScopedConfigService
from msflib.workspaces.actions import UserAction, WorkspaceAction
from msflib.workspaces.models import (
    UserCreate,
    UserUpdate,
    WorkspaceCreate,
    WorkspaceStatus,
    WorkspaceUpdate,
)
from msflib.workspaces.models.user import User
from msflib.workspaces.models.workspace import Workspace
from sqlmodel import Session

from app.core.config import settings
from app.models import Account

logger = logging.getLogger(__name__)

workspace_action = WorkspaceAction[Workspace, WorkspaceCreate, WorkspaceUpdate](settings=settings)
user_action = UserAction[User, UserCreate, UserUpdate]()
scoped_config = ScopedConfigService()


def default_tenant(session: Session) -> Tenant:
    tenant_id = resolve_default_tenant_id(session, settings=settings.scope("TENANCY"))
    session.commit()
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise RuntimeError("The default tenant could not be resolved.")
    return tenant


def ensure_membership(session: Session, account: Account) -> Workspace:
    """Join the account to the tenant's default workspace."""
    tenant = default_tenant(session)
    workspace = workspace_action.ensure_default_workspace(
        session,
        owner_id=int(account.id),
        tenant=tenant,
        commit=False,
    )
    user_action.create_membership(
        session,
        account_id=int(account.id),
        workspace_id=int(workspace.id),
        owner_id=int(workspace.owner_id),
        commit=False,
    )
    if account.current_workspace_id is None:
        account.current_workspace_id = workspace.id
        session.add(account)
    session.commit()
    session.refresh(workspace)
    return workspace


def provision_organization_workspace(
    session: Session,
    account: Account,
    organization_name: str,
) -> Workspace:
    """Give a buyer organization its own workspace and NGN procurement config."""
    tenant = default_tenant(session)
    slug = re.sub(r"[^a-z0-9]+", "-", organization_name.lower()).strip("-") or "buyer"
    workspace = workspace_action.create(
        session,
        data=WorkspaceCreate(
            name=organization_name,
            slug=slug,
            description=f"Procurement workspace for {organization_name}",
            owner_id=int(account.id),
            status=WorkspaceStatus.open,
            is_default=False,
        ),
        update={"tenant_id": tenant.id},
        commit=False,
    )
    user_action.create_membership(
        session,
        account_id=int(account.id),
        workspace_id=int(workspace.id),
        owner_id=int(account.id),
        commit=False,
    )
    account.current_workspace_id = workspace.id
    session.add(account)
    session.commit()
    session.refresh(workspace)

    scoped_config.set_value(
        session,
        ConfigScopeType.workspace,
        "PROCUREMENT",
        "CURRENCY",
        "NGN",
        workspace_id=int(workspace.id),
    )
    logger.info("Provisioned workspace %s for account %s", workspace.slug, account.id)
    return workspace
