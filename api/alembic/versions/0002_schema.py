"""schema

Revision ID: 0002_schema
Revises: 0001_baseline
Create Date: 2026-09-22

Core schema for Module 01: role, user (+ user_backup_code), import_batch,
applicant, application_status_event, finance_record, payment_claim,
audit_log. Hand-written (not autogenerate output) so the ordering, enum
creation, and the finance_record admission-gate trigger are all deliberate
and reviewed together rather than autogenerate's own column ordering.

Table creation order follows FK dependency: role -> user -> import_batch ->
applicant -> application_status_event / finance_record -> payment_claim ->
audit_log.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_schema"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

application_status_enum = postgresql.ENUM(
    "INQUIRY",
    "APPLICATION_STARTED",
    "DOCUMENTS_SUBMITTED",
    "UNDER_REVIEW",
    "OFFER_MADE",
    "ADMISSION_TAKEN",
    "REJECTED",
    "WITHDRAWN",
    name="application_status",
)
import_batch_status_enum = postgresql.ENUM(
    "PENDING", "PROCESSING", "COMPLETED", "FAILED", name="import_batch_status"
)
payment_claim_status_enum = postgresql.ENUM(
    "PENDING", "CONFIRMED", "REJECTED", name="payment_claim_status"
)

# The three ENUM objects above are used once each to explicitly CREATE TYPE
# (checkfirst=True) at the top of upgrade(). The column-level references
# below reuse the *same type name* but with create_type=False -- without
# that flag, SQLAlchemy's DDL visitor for a postgresql.ENUM column tries to
# CREATE TYPE a second time (once per table it is used on) via
# CREATE TABLE's own "before_create" event, which collides with a type this
# migration already created explicitly and raises DuplicateObjectError.
# Confirmed by running this migration against the real stack: it failed
# with exactly that error before create_type=False was added here.
_application_status_col = postgresql.ENUM(
    "INQUIRY",
    "APPLICATION_STARTED",
    "DOCUMENTS_SUBMITTED",
    "UNDER_REVIEW",
    "OFFER_MADE",
    "ADMISSION_TAKEN",
    "REJECTED",
    "WITHDRAWN",
    name="application_status",
    create_type=False,
)
_import_batch_status_col = postgresql.ENUM(
    "PENDING", "PROCESSING", "COMPLETED", "FAILED", name="import_batch_status", create_type=False
)
_payment_claim_status_col = postgresql.ENUM(
    "PENDING", "CONFIRMED", "REJECTED", name="payment_claim_status", create_type=False
)


def upgrade() -> None:
    application_status_enum.create(op.get_bind(), checkfirst=True)
    import_batch_status_enum.create(op.get_bind(), checkfirst=True)
    payment_claim_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "role",
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_role_code"),
    )

    op.create_table(
        "user",
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("totp_secret_encrypted", sa.String(), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_user_email"),
    )

    op.create_table(
        "user_backup_code",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "code_hash", name="uq_backup_code_per_user"),
    )

    op.create_table(
        "import_batch",
        sa.Column("source_filename", sa.String(), nullable=False),
        sa.Column("status", _import_batch_status_col, nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("error_detail", sa.String(), nullable=True),
        sa.Column("imported_by", sa.UUID(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["imported_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "applicant",
        sa.Column("import_batch_id", sa.UUID(), nullable=True),
        sa.Column("assigned_counselor_id", sa.UUID(), nullable=True),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("program", sa.String(), nullable=False),
        sa.Column("intake_cycle", sa.String(), nullable=False),
        sa.Column("current_status", _application_status_col, nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batch.id"]),
        sa.ForeignKeyConstraint(["assigned_counselor_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_applicant_assigned_counselor_id", "applicant", ["assigned_counselor_id"])
    op.create_index("ix_applicant_current_status", "applicant", ["current_status"])

    op.create_table(
        "application_status_event",
        sa.Column("applicant_id", sa.UUID(), nullable=False),
        sa.Column("from_status", _application_status_col, nullable=True),
        sa.Column("to_status", _application_status_col, nullable=False),
        sa.Column("changed_by", sa.UUID(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(["applicant_id"], ["applicant.id"]),
        sa.ForeignKeyConstraint(["changed_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_application_status_event_applicant_id", "application_status_event", ["applicant_id"]
    )

    op.create_table(
        "finance_record",
        sa.Column("applicant_id", sa.UUID(), nullable=False),
        sa.Column("total_fee_due", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_paid", sa.Numeric(12, 2), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["applicant_id"], ["applicant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("applicant_id", name="uq_finance_record_applicant"),
    )

    op.create_table(
        "payment_claim",
        sa.Column("finance_record_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", _payment_claim_status_col, nullable=False),
        sa.Column("submitted_by", sa.UUID(), nullable=False),
        sa.Column("confirmed_by", sa.UUID(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["finance_record_id"], ["finance_record.id"]),
        sa.ForeignKeyConstraint(["submitted_by"], ["user.id"]),
        sa.ForeignKeyConstraint(["confirmed_by"], ["user.id"]),
        sa.CheckConstraint(
            "confirmed_by IS NULL OR confirmed_by <> submitted_by",
            name="ck_payment_claim_distinct_submitter_confirmer",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_claim_finance_record_id", "payment_claim", ["finance_record_id"])

    op.create_table(
        "audit_log",
        sa.Column("table_name", sa.String(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("client_ip", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_table_name_record_id", "audit_log", ["table_name", "record_id"])

    # ADR-07/module scope: finance_record is a one-to-zero-or-one child of
    # applicant created ONLY once the applicant's status reaches
    # ADMISSION_TAKEN. The unique constraint above enforces the
    # "zero-or-one" cardinality; this trigger enforces the "only when
    # Admission Taken" business rule at the database, so no code path --
    # including a raw SQL insert run by hand -- can create an orphaned
    # finance_record for an applicant who never reached that status.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_record_requires_admission_taken() RETURNS trigger AS $$
        DECLARE
            v_status application_status;
        BEGIN
            SELECT current_status INTO v_status FROM applicant WHERE id = NEW.applicant_id;
            IF v_status IS DISTINCT FROM 'ADMISSION_TAKEN' THEN
                RAISE EXCEPTION
                    'finance_record can only be created for an applicant whose current_status is ADMISSION_TAKEN (was %)',
                    v_status;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER finance_record_admission_gate
        BEFORE INSERT ON finance_record
        FOR EACH ROW EXECUTE FUNCTION finance_record_requires_admission_taken()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS finance_record_admission_gate ON finance_record")
    op.execute("DROP FUNCTION IF EXISTS finance_record_requires_admission_taken()")

    op.drop_index("ix_audit_log_table_name_record_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_payment_claim_finance_record_id", table_name="payment_claim")
    op.drop_table("payment_claim")
    op.drop_table("finance_record")
    op.drop_index(
        "ix_application_status_event_applicant_id", table_name="application_status_event"
    )
    op.drop_table("application_status_event")
    op.drop_index("ix_applicant_current_status", table_name="applicant")
    op.drop_index("ix_applicant_assigned_counselor_id", table_name="applicant")
    op.drop_table("applicant")
    op.drop_table("import_batch")
    op.drop_table("user_backup_code")
    op.drop_table("user")
    op.drop_table("role")

    payment_claim_status_enum.drop(op.get_bind(), checkfirst=True)
    import_batch_status_enum.drop(op.get_bind(), checkfirst=True)
    application_status_enum.drop(op.get_bind(), checkfirst=True)
