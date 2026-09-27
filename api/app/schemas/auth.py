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
    """`GET /auth/me`. `pending_email` (Module 17, `None` unless a
    self-service email-change is genuinely in flight for this account)
    is the frontend's own decided-and-implemented visibility choice --
    see `app.routers.auth.me`'s own docstring for the full reasoning on
    why an in-flight change is shown, not hidden.
    """

    user_id: uuid.UUID
    email: str
    full_name: str
    role_code: str
    totp_enabled: bool
    pending_email: str | None = None


class ChangePasswordRequest(BaseModel):
    """`POST /auth/change-password` (Module 15). No user id field --
    `app.routers.auth.change_password` sources the target account
    exclusively from the authenticated session itself, the same
    "trust the session, never the body" rule already established for
    `submitted_by` on payment claims (`app.schemas.payment_claim`'s own
    docstring). A change-password request that carried its own user id
    would let any authenticated session change any other account's
    password merely by naming its id in the body -- there is no
    legitimate reason for this field to ever exist here.
    """

    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    """`POST /auth/forgot-password` (Module 16). Unauthenticated by
    definition -- a locked-out user has no session. Takes only an email;
    the response is always the same generic success shape regardless of
    whether that email exists (see the route's own docstring), so this
    schema deliberately has no field that could ever appear in the
    response.
    """

    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    """The one, unconditional response shape `POST /auth/forgot-password`
    ever returns -- see that route's own docstring for the anti-
    enumeration reasoning. `message` is a fixed string, not templated
    with anything request-specific (no echoed email, no user id, no
    token, no indication of whether a real account was found).
    """

    message: str


class ResetPasswordRequest(BaseModel):
    """`POST /auth/reset-password` (Module 16). `token` is the raw,
    single-use value from the email link -- never a user id or email;
    the token alone both identifies the account and proves the requester
    controls the mailbox that received it, the same two-factor-of-
    identity property a TOTP backup code has for its own account.
    """

    token: str
    new_password: str


class ChangeEmailRequest(BaseModel):
    """`POST /auth/change-email` (Module 17). Authenticated -- requires
    the caller's own already-verified session, the same
    `get_current_user` dependency `change_password` uses, since this
    mutates a security-sensitive identity field. Takes only the
    proposed new address; the account's *current* email is sourced
    exclusively from the session, never the request body, the same
    "trust the session" rule `ChangePasswordRequest`'s own docstring
    already establishes.
    """

    new_email: EmailStr


class ChangeEmailResponse(BaseModel):
    """Confirms the request was accepted and a confirmation email was
    sent to `new_email` -- deliberately does not confirm whether
    `new_email` is *available* (not already in use by a different
    account); see `app.routers.auth.change_email`'s own docstring for
    why that check is silent by design, the same anti-enumeration
    reasoning `POST /auth/forgot-password` already established, applied
    here to prevent an authenticated caller from using this endpoint to
    probe which arbitrary addresses are already registered accounts.
    """

    message: str


class ConfirmEmailChangeRequest(BaseModel):
    """`POST /auth/confirm-email-change` (Module 17). Unauthenticated --
    the raw token from the confirmation email is the caller's entire
    proof they control the new mailbox, the same shape
    `ResetPasswordRequest` already establishes for password tokens.
    """

    token: str
