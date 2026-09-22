"""Native Postgres enum types shared across models.

These map to `CREATE TYPE ... AS ENUM (...)` in Postgres, not a Python-side
CHECK constraint. Status-transition validation (which values an applicant
may move between) is the next module's service-layer responsibility; this
module only creates the type, the column, and the append-only event log the
next module will write to.
"""

import enum


class ApplicationStatus(str, enum.Enum):
    INQUIRY = "INQUIRY"
    APPLICATION_STARTED = "APPLICATION_STARTED"
    DOCUMENTS_SUBMITTED = "DOCUMENTS_SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    OFFER_MADE = "OFFER_MADE"
    ADMISSION_TAKEN = "ADMISSION_TAKEN"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class ImportBatchStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PaymentClaimStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class RoleCode(str, enum.Enum):
    """Stable, machine-facing identifiers -- distinct from `role.name`, the
    human-readable display label. RBAC dependencies and RLS policies key off
    this code, never off the display name, so renaming a role for display
    purposes never touches access-control logic.
    """

    SUPER_ADMIN = "SUPER_ADMIN"
    ADMISSIONS_MANAGER = "ADMISSIONS_MANAGER"
    ADMISSIONS_COUNSELOR = "ADMISSIONS_COUNSELOR"
    FINANCE_STAFF = "FINANCE_STAFF"
    FINANCE_MANAGER = "FINANCE_MANAGER"
    AUDITOR = "AUDITOR"


# Roles that must complete mandatory TOTP enrollment before their session is
# considered fully authenticated (module prompt: "enforced at minimum for
# the Super Admin, Finance Staff, and Finance Manager roles").
MANDATORY_TOTP_ROLES = frozenset(
    {RoleCode.SUPER_ADMIN, RoleCode.FINANCE_STAFF, RoleCode.FINANCE_MANAGER}
)
