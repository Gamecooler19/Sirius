"""Import every model so `Base.metadata` (used by Alembic autogenerate and
by any test setup) sees the complete schema.
"""

from app.models.applicant import Applicant
from app.models.application_status_event import ApplicationStatusEvent
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.finance_record import FinanceRecord
from app.models.import_batch import ImportBatch
from app.models.password_reset_token import PasswordResetToken
from app.models.payment_claim import PaymentClaim
from app.models.push_subscription import PushSubscription
from app.models.role import Role
from app.models.user import User, UserBackupCode

__all__ = [
    "Applicant",
    "ApplicationStatusEvent",
    "AuditLog",
    "Base",
    "FinanceRecord",
    "ImportBatch",
    "PasswordResetToken",
    "PaymentClaim",
    "PushSubscription",
    "Role",
    "User",
    "UserBackupCode",
]
