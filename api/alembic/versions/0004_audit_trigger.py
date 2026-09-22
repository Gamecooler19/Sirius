"""audit_trigger

Revision ID: 0004_audit_trigger
Revises: 0003_rls
Create Date: 2026-09-22

ADR-07: trigger-based audit, not an application-level helper. `write_audit()`
fires `AFTER INSERT OR UPDATE OR DELETE FOR EACH ROW` on every mutable
business table and writes into the single generic `audit_log` table, keyed
by `table_name` + `record_id` (module scope: one generic audit table, not
one per entity).

`"user"` and `"role"` are quoted throughout this migration's raw SQL --
`user` is a reserved word in Postgres's grammar (unquoted `user` in a
`CREATE TRIGGER ... ON user` statement is a syntax error), and `role`,
while not strictly reserved, is quoted for the same consistency.

`audit_log` also gets a second trigger, `audit_log_block_mutation`, that
raises on UPDATE or DELETE -- an audit trail that can be edited after the
fact is not an audit trail.

`updated_at` maintenance also lives here as a trigger (`set_updated_at`),
covering every table carrying that column, so it stays correct even for a
raw-SQL fix applied by hand in a console.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_audit_trigger"
down_revision: str | None = "0003_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every table that gets write_audit() -- every mutable business table minus
# audit_log itself (which must never audit its own writes, or every insert
# would recurse forever).
AUDITED_TABLES = [
    '"role"',
    '"user"',
    "user_backup_code",
    "import_batch",
    "applicant",
    "application_status_event",
    "finance_record",
    "payment_claim",
]

# Tables carrying updated_at that need the maintenance trigger.
# user_backup_code and application_status_event have no updated_at (both
# are effectively append-only/immutable-after-insert rows), so they are
# excluded here.
TIMESTAMPED_TABLES = [
    '"role"',
    '"user"',
    "import_batch",
    "applicant",
    "finance_record",
    "payment_claim",
]

WRITE_AUDIT_FUNCTION = """
CREATE OR REPLACE FUNCTION write_audit() RETURNS trigger AS $$
DECLARE
    v_record_id uuid;
    v_actor_id uuid;
    v_client_ip text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_record_id := OLD.id;
    ELSE
        v_record_id := NEW.id;
    END IF;

    BEGIN
        v_actor_id := NULLIF(current_setting('app.actor_id', true), '')::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
        v_actor_id := NULL;
    END;

    v_client_ip := NULLIF(current_setting('app.client_ip', true), '');

    INSERT INTO audit_log (
        id, table_name, record_id, action, before, after, actor_id, client_ip, created_at
    )
    VALUES (
        gen_random_uuid(),
        TG_TABLE_NAME,
        v_record_id,
        TG_OP,
        CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) ELSE NULL END,
        CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) ELSE NULL END,
        v_actor_id,
        v_client_ip,
        now()
    );

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_log_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""

SET_UPDATED_AT_FUNCTION = """
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(WRITE_AUDIT_FUNCTION)
    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(SET_UPDATED_AT_FUNCTION)

    for table in AUDITED_TABLES:
        trigger_name = table.strip('"') + "_write_audit"
        op.execute(
            f"""
            CREATE TRIGGER {trigger_name}
            AFTER INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION write_audit()
            """
        )

    for table in TIMESTAMPED_TABLES:
        trigger_name = table.strip('"') + "_set_updated_at"
        op.execute(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
            """
        )

    op.execute(
        """
        CREATE TRIGGER audit_log_append_only
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_block_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log")

    for table in TIMESTAMPED_TABLES:
        trigger_name = table.strip('"') + "_set_updated_at"
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table}")

    for table in AUDITED_TABLES:
        trigger_name = table.strip('"') + "_write_audit"
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table}")

    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.execute("DROP FUNCTION IF EXISTS audit_log_block_mutation()")
    op.execute("DROP FUNCTION IF EXISTS write_audit()")
