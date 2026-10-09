from msflib.account.config import AccountSettings
from msflib.ai_core.config import AICoreSettings
from msflib.auth.config import AuthSettings
from msflib.core.config import CoreSettings, SettingsBase
from msflib.notifications.config import NotificationSettings
from msflib.payments.config import PaymentsSettings


class Settings(
    NotificationSettings,
    PaymentsSettings,
    AICoreSettings,
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


settings = Settings()
