from typing import ClassVar

from msflib.core.config import ModuleSettingsBase
from msflib.policy import PolicyEnvelope


class RoutingPolicy(PolicyEnvelope):
    currency: str = "NGN"
    analysis_model: str = "openai/gpt-4o-mini"


class ProcurementSettings(ModuleSettingsBase):
    """Tiered procurement settings. Tenant, workspace, and user values override these."""

    namespace: ClassVar[str] = "PROCUREMENT"
    request_override_allowlist: ClassVar[set[str]] = {"ANALYSIS_MODEL", "CURRENCY"}

    CURRENCY: str = "NGN"
    ANALYSIS_MODEL: str = "openai/gpt-4o-mini"
    ROUTING_POLICY: RoutingPolicy = RoutingPolicy()
