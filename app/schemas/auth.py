from typing import Literal

from pydantic import BaseModel, EmailStr, Field
from msflib.account.models import ProfileCreate


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    account_type: Literal["buyer", "vendor"]
    username: str | None = None
    phone: str | None = None
    profile: ProfileCreate | None = None
