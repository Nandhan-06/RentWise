"""schemas.py — request/response models for Module 1 endpoints."""

from datetime import date, time
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


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

    @field_validator("name", "phone", mode="before")
    @classmethod
    def _strip(cls, v):
        # "   " must not count as a name, and stray spaces around a phone
        # number shouldn't be stored.
        return v.strip() if isinstance(v, str) else v


PROPERTY_TYPES = ("Apartment", "Villa", "Independent House", "Studio", "PG")
FURNISHING_TYPES = ("Furnished", "Semi-Furnished", "Unfurnished")


class PreferencesUpdate(BaseModel):
    """Module 11: a user's rental preferences. Every field is optional - blank
    means "no preference". PUT /users/me/preferences REPLACES the whole set, so
    a field left out (or null) is cleared."""

    preferred_city: Optional[str] = Field(default=None, max_length=100)
    min_budget: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    max_budget: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    bedrooms: Optional[int] = Field(default=None, ge=0, le=10)
    property_type: Optional[Literal["Apartment", "Villa", "Independent House", "Studio", "PG"]] = None
    furnishing: Optional[Literal["Furnished", "Semi-Furnished", "Unfurnished"]] = None
    needs_parking: bool = False

    @field_validator("preferred_city", "property_type", "furnishing", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        # A form field left empty arrives as "" - treat it as "no preference".
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @model_validator(mode="after")
    def _budget_order(self):
        if self.min_budget is not None and self.max_budget is not None and self.min_budget > self.max_budget:
            raise ValueError("Minimum budget can't be higher than maximum budget")
        return self


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


class ContactCreate(BaseModel):
    """Module 9: Contact page form."""

    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    topic: Literal[
        "General question",
        "Problem with a listing",
        "Visit booking",
        "My account",
        "Feedback",
        "Other",
    ]
    message: str = Field(..., min_length=10, max_length=2000)
    # Honeypot: hidden in the page, so real people leave it empty. Bots that
    # fill in every field give themselves away (see POST /contact).
    website: Optional[str] = Field(default=None, max_length=200)

    @field_validator("name", "message", mode="before")
    @classmethod
    def _strip(cls, v):
        # Strip first so "   " counts as empty and trailing spaces don't count
        # towards the length limits.
        return v.strip() if isinstance(v, str) else v
