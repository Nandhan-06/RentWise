"""schemas.py — request/response models for Module 1 endpoints."""

from datetime import date, time
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, model_validator


class FavoriteCreate(BaseModel):
    property_id: int


class VisitCreate(BaseModel):
    property_id: int
    visit_date: date
    visit_time: time


class PropertyFilterParams(BaseModel):
    city: Optional[str] = None
    property_type: Optional[str] = None
    min_rent: Optional[float] = Field(default=None, ge=0)
    max_rent: Optional[float] = Field(default=None, ge=0)
    bedrooms: Optional[int] = Field(default=None, ge=0)
    furnishing: Optional[str] = None
    parking: Optional[bool] = None


class AISearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[EmailStr] = None


class CompareRequest(BaseModel):
    property_ids: List[int] = Field(..., min_length=2, max_length=3)


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., max_length=1000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    history: List[ChatMessage] = Field(default_factory=list, max_length=20)


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=20)
    password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str
    terms_accepted: bool
    register_as_landlord: bool = False

    @model_validator(mode="after")
    def _check(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        if not self.terms_accepted:
            raise ValueError("You must accept the Terms to sign up")
        return self


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
