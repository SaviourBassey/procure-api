"""Resolve procurement settings across the msflib policy tiers."""

from msflib.policy import InMemoryPolicyDecisionLogger, PolicyResolutionService
from msflib.scope import PrincipalContext, ScopeCompiler, ScopeEnvelope, create_default_registry
from msflib.workspace_config.service import ScopedConfigPolicyStoreAdapter, ScopedConfigService
from sqlmodel import Session

from app.core.procurement import ProcurementSettings
from app.models import Account

_decisions = InMemoryPolicyDecisionLogger()
_policy = PolicyResolutionService(
    scoped_config_store=ScopedConfigPolicyStoreAdapter(ScopedConfigService()),
    decision_logger=_decisions,
)
_compiler = ScopeCompiler(registry=create_default_registry())


def resolve_procurement(session: Session, account: Account | None = None):
    workspace_id = getattr(account, "current_workspace_id", None) if account else None
    account_id = int(account.id) if account is not None and account.id is not None else None
    tenant_id = None
    if account is not None:
        from msflib.tenancy.resolver import resolve_default_tenant_id

        from app.core.config import settings

        tenant_id = resolve_default_tenant_id(
            session,
            settings=settings.scope("TENANCY"),
            create_if_missing=False,
        )

    resolved, trace = _policy.resolve_module_settings(
        ProcurementSettings(),
        session=session,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        account_id=account_id,
        trace_policy_field="CURRENCY",
    )
    envelope = ScopeEnvelope(
        dimensions={
            "tenant_id": None if tenant_id is None else str(tenant_id),
            "workspace_id": None if workspace_id is None else str(workspace_id),
        },
        principal=PrincipalContext(account_id=None if account_id is None else str(account_id)),
    )
    scope = _compiler.compile_scope_string(envelope, operation="retrieval.search")
    return resolved, trace, scope
