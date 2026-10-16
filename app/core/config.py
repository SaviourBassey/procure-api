from msflib.account.config import AccountSettings
from msflib.ai_core.config import AICoreSettings
from msflib.auth.config import AuthSettings
from msflib.conversation.config import ConversationSettings
from msflib.core.config import CoreSettings, SettingsBase
from msflib.documents.config import DocumentsSettings
from msflib.drivelink.config import DrivelinkSettings
from msflib.ingestion.config import IngestionSettings
from msflib.knowledge.config import GraphBackend, KnowledgeSettings
from msflib.notifications.config import NotificationSettings
from msflib.payments.config import PaymentsSettings
from msflib.tenancy.config import TenancySettings
from msflib.workspace_config.config import WorkspaceConfigSettings
from msflib.workspace_notifications.config import WsNotificationSettings
from msflib.workspaces.config import WorkspaceSettings

from app.core.procurement import ProcurementSettings


class Settings(
    ProcurementSettings,
    NotificationSettings,
    PaymentsSettings,
    AICoreSettings,
    ConversationSettings,
    DocumentsSettings,
    DrivelinkSettings,
    IngestionSettings,
    KnowledgeSettings,
    TenancySettings,
    WorkspaceSettings,
    WorkspaceConfigSettings,
    WsNotificationSettings,
    AccountSettings,
    AuthSettings,
    CoreSettings,
    SettingsBase,
):
    PROJECT_NAME: str = "Procure API"
    SECRET_KEY: str = "development-only-change-this-before-deployment"
    USERS_OPEN_REGISTRATION: bool = False
    EMAILS_ENABLED: bool = False
    # Long enough for the eight-section procurement report.
    LLM_MAX_TOKENS: int | None = 4096
    LLM_TEMPERATURE: float = 0.0

    DEFAULT_TENANT_SLUG: str = "procure"
    DEFAULT_TENANT_NAME: str = "Procure"

    # Document and knowledge jobs stay registered, but they do not require a
    # Redis worker unless an operator turns the queues on.
    QUEUE_ENABLED: bool = False
    EXTRACTION_QUEUE_ENABLED: bool = False
    RECORD_QUEUE_ENABLED: bool = False
    GRAPH_BACKEND: GraphBackend = GraphBackend.none


settings = Settings()
