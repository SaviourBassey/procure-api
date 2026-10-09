from msflib.account.config import AccountSettings
from msflib.auth.config import AuthSettings
from msflib.core.config import CoreSettings, SettingsBase


class Settings(AccountSettings, AuthSettings, CoreSettings, SettingsBase):
    PROJECT_NAME: str = "Procure API"
    SECRET_KEY: str = "development-only-change-this-before-deployment"
    USERS_OPEN_REGISTRATION: bool = False
    EMAILS_ENABLED: bool = False


settings = Settings()
