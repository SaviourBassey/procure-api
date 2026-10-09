from msflib.account.actions import AccountAction, ProfileAction
from msflib.account.models import (
    AccountCreate,
    AccountUpdate,
    ProfileCreate,
    ProfileUpdate,
)

from app.core.config import settings
from app.models import Account, Profile

profile_action = ProfileAction[
    Profile, ProfileCreate, ProfileUpdate
]()

account_action = AccountAction[
    Account, AccountCreate, AccountUpdate
](
    settings=settings,
    profile_action=profile_action,
)
