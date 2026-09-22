"""Request/response schemas for the auth router."""

import uuid

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """`totp_required` tells the client whether to prompt for a TOTP code
    next (mandatory-TOTP role that has completed enrollment) or for
    enrollment itself (`totp_enrollment_required`) before the session is
    usable for any protected route.
    """

    user_id: uuid.UUID
    role_code: str
    totp_required: bool
    totp_enrollment_required: bool


class TotpEnrollStartResponse(BaseModel):
    provisioning_uri: str
    backup_codes: list[str]


class TotpEnrollConfirmRequest(BaseModel):
    code: str


class TotpVerifyRequest(BaseModel):
    code: str


class TotpBackupCodeRequest(BaseModel):
    backup_code: str


class MeResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role_code: str
    totp_enabled: bool
