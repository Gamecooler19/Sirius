"""Request/response schemas for user administration (Module 15).

Every response model here is hand-declared, never `from_attributes=True`
over the raw `User` ORM object -- the same rule `app.schemas.reads`'
own docstring establishes, and it matters more here than almost anywhere
else in this codebase: `User` carries `password_hash` and
`totp_secret_encrypted` directly on the row. A response model built from
`User.__dict__` would leak both the instant a route author forgot to
explicitly exclude them. `UserSummary` below lists every field it
returns; there is no path for a column added to `User` later to appear
on the wire without a matching, deliberate addition here.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.enums import RoleCode


class UserSummary(BaseModel):
    """One row of `GET /users`, and the shape `POST /users`/
    `PATCH /users/{id}` both return after their own write. Deliberately
    excludes `password_hash` and `totp_secret_encrypted` -- see this
    module's own docstring.
    """

    id: uuid.UUID
    email: str
    full_name: str
    role_code: str
    is_active: bool
    totp_enabled: bool
    last_login_at: datetime | None
    created_at: datetime


class UserListResponse(BaseModel):
    items: list[UserSummary]
    total: int
    limit: int
    offset: int


class UserCreateRequest(BaseModel):
    """`POST /users` (`SUPER_ADMIN` only). `full_name` is required --
    every other write path that creates a `User` row in this codebase
    (Module 11's manual seed inserts) has always populated it, and there
    is no legitimate "nameless account" case for an admin-created user.

    Deliberately has no `is_active` or `totp_enabled` field: a new
    account is always created active (an admin creating a disabled
    account is not a real use case this module supports; deactivation is
    a separate, explicit `PATCH` afterward) and always with
    `totp_enabled=False` -- see `app.routers.users.create_user`'s own
    docstring for why that specific default is load-bearing, not
    incidental.
    """

    email: EmailStr
    full_name: str
    password: str
    role_code: RoleCode


class UserUpdateRequest(BaseModel):
    """`PATCH /users/{id}` (`SUPER_ADMIN` only). Both fields optional --
    a caller changing only role or only active-status sends just that
    one field; `None` (the default) means "leave this field alone,"
    distinct from an explicit value. Pydantic's own `model_fields_set`
    is checked in the route itself to tell "field omitted" apart from "
    field explicitly sent" for `is_active` (a `bool`, where `None` can't
    double as "omitted" the way it naturally can for `role_code`).
    """

    role_code: RoleCode | None = None
    is_active: bool | None = None
