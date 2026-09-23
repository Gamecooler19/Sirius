"""Native Postgres enum types shared across models.

These map to `CREATE TYPE ... AS ENUM (...)` in Postgres, not a Python-side
CHECK constraint. Status-transition validation (which values an applicant
may move between) is the next module's service-layer responsibility; this
module only creates the type, the column, and the append-only event log the
next module will write to.
"""

import enum


class ApplicationStatus(str, enum.Enum):
    """The agreed admissions pipeline. `IMPORTED` is the default status a
    freshly-imported applicant gets (Module 02's Excel-import endpoint).
    `ENROLLED` is deliberately not part of this vocabulary -- out of scope
    for now; see migration `0006_status_enum_rename` for the correction
    that fixed a naming drift from an earlier, unilaterally-chosen set
    (`INQUIRY`/`APPLICATION_STARTED`/`DOCUMENTS_SUBMITTED`/`UNDER_REVIEW`/
    `OFFER_MADE`) to this one. Valid transitions between these values are
    enforced by `app.services.status_transitions`, not by this enum.
    """

    IMPORTED = "IMPORTED"
    APPLIED = "APPLIED"
    IN_PROCESS = "IN_PROCESS"
    ON_HOLD = "ON_HOLD"
    ADMISSION_OFFERED = "ADMISSION_OFFERED"
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


class PaymentMode(str, enum.Enum):
    """Closed vocabulary for how a payment claim's money was actually
    moved -- matches this project's existing precedent of a native enum
    over free text for a closed-vocabulary field (e.g. `ApplicationStatus`).
    """

    CASH = "CASH"
    CHEQUE = "CHEQUE"
    BANK_TRANSFER = "BANK_TRANSFER"
    UPI = "UPI"
    CARD = "CARD"
    OTHER = "OTHER"


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
