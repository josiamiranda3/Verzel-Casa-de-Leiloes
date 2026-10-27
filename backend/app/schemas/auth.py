
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints
from typing import Annotated, Literal


PasswordInput = Annotated[
    str,
    StringConstraints(min_length=8, max_length=128),
]


class UserRegister(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: PasswordInput
    role: Literal["auctioneer", "bidder"]


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: Literal["auctioneer", "bidder"]

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
