from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator
from app.models import UserRole, JobStatus


class UserBase(BaseModel):
    email: EmailStr
    role: UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: UserRole = UserRole.user

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class UserUpdate(BaseModel):
    role: Optional[UserRole] = None
    password: Optional[str] = None


class UserOut(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ActionDefinitionBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    input_sequence: str
    result_regex: str
    timeout_seconds: Optional[int] = None
    is_enabled: bool = True


class ActionDefinitionCreate(ActionDefinitionBase):
    pass


class ActionDefinitionUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    input_sequence: Optional[str] = None
    result_regex: Optional[str] = None
    timeout_seconds: Optional[int] = None
    is_enabled: Optional[bool] = None


class ActionDefinitionOut(ActionDefinitionBase):
    id: int
    created_at: datetime
    updated_at: datetime
    created_by_user_id: Optional[int] = None

    class Config:
        from_attributes = True


class ActionJobCreate(BaseModel):
    pass


class ActionJobOut(BaseModel):
    id: int
    action_definition_id: int
    requested_by_user_id: int
    action_name: Optional[str] = None
    requested_by_email: Optional[str] = None
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    raw_request_payload: Optional[str]
    raw_response: Optional[str]
    parsed_result: Optional[str]
    error_message: Optional[str]

    class Config:
        from_attributes = True


class RegexTestRequest(BaseModel):
    sample_text: str
    regex: str


class RegexTestResponse(BaseModel):
    matches: list[str]
    groups: dict[str, str | None]
