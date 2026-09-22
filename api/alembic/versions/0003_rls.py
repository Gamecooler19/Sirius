"""row_level_security

Revision ID: 0003_rls
Revises: 0002_schema
Create Date: 2026-09-22

Enables row-level security on every business table except role, user, and
user_backup_code (the identity axis -- see ADR-03). Two details matter for
this to be real isolation rather than a policy that silently does nothing
(ADR-02):

1. `ALTER TABLE ... FORCE ROW LEVEL SECURITY`. Without `FORCE`, a table's
   *owner* bypasses RLS entirely by default, and the application connects
   as the owning role (`univadmissions`, the role that ran this migration
   and created these tables). A policy without `FORCE` looks correct in
   `\\d+` and protects nothing -- exactly the GeM defect ADR-02 documents.

2. Every `current_setting()` call is wrapped in `NULLIF(..., '')` per
   ADR-01's own reasoning about pooled-backend GUC reset values.

Policy shape per ADR-03: `app.actor_role` decides which roles see a table
at all (a fixed allowlist per table); `applicant`/`application_status_event`
additionally restrict `ADMISSIONS_COUNSELOR` to their own assigned rows via
`app.actor_id`.

**`audit_log` is a deliberate, structural exception to the "USING and WITH
CHECK share one predicate" pattern every other table here uses.** Every row
in `audit_log` is written exclusively by the `write_audit()` trigger
(ADR-07), never by application code directly, and that trigger fires on
every INSERT/UPDATE/DELETE against *any* audited table regardless of which
role performed it -- an `ADMISSIONS_COUNSELOR` creating an applicant causes
`write_audit()` to insert into `audit_log` on their behalf. If `audit_log`'s
INSERT check required `app.actor_role IN ('SUPER_ADMIN', 'AUDITOR')` (the
same predicate that correctly restricts who may *read* it), every write by
every other role would fail with "new row violates row-level security
policy for table audit_log" -- confirmed for real running this migration's
first draft against the live stack: even the seed-roles migration itself
(no `app.actor_role` GUC set at all, since migrations run outside a
request) failed this way the moment `write_audit()` tried to record the
first seeded role. `audit_log` therefore gets two separate policies instead
of one: `audit_log_select` (`FOR SELECT`, the role allowlist, unchanged)
and `audit_log_insert` (`FOR INSERT`, `WITH CHECK (true)`, unconditional) --
reads stay restricted to `SUPER_ADMIN`/`AUDITOR`; the trigger's own writes,
the only writes `audit_log` structurally accepts, are never blocked by a
role check that was never about the trigger in the first place.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_rls"
down_revision: str | None = "0002_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTOR_ROLE = "NULLIF(current_setting('app.actor_role', true), '')"
_ACTOR_ID = "NULLIF(current_setting('app.actor_id', true), '')::uuid"

# Tables where every allowed role sees every row (no per-row ownership
# filter beyond the role allowlist itself).
_ROLE_ONLY_POLICIES: dict[str, tuple[str, ...]] = {
    "import_batch": ("SUPER_ADMIN", "ADMISSIONS_MANAGER", "AUDITOR"),
    "finance_record": ("SUPER_ADMIN", "FINANCE_STAFF", "FINANCE_MANAGER", "AUDITOR"),
    "payment_claim": ("SUPER_ADMIN", "FINANCE_STAFF", "FINANCE_MANAGER", "AUDITOR"),
    "audit_log": ("SUPER_ADMIN", "AUDITOR"),
}

_ALL_APPLICANT_VISIBLE_ROLES = (
    "SUPER_ADMIN",
    "ADMISSIONS_MANAGER",
    "FINANCE_STAFF",
    "FINANCE_MANAGER",
    "AUDITOR",
)


def _role_in(roles: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{r}'" for r in roles)
    return f"{_ACTOR_ROLE} IN ({quoted})"


def upgrade() -> None:
    for table, roles in _ROLE_ONLY_POLICIES.items():
        predicate = _role_in(roles)
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        if table == "audit_log":
            # See this migration's own module docstring: audit_log's
            # writes come exclusively from the write_audit() trigger
            # (ADR-07), which fires regardless of the acting role, so the
            # INSERT check must be unconditional. Only SELECT is restricted
            # to the role allowlist.
            op.execute(
                f"""
                CREATE POLICY audit_log_select ON {table}
                FOR SELECT
                USING ({predicate})
                """
            )
            op.execute(
                f"""
                CREATE POLICY audit_log_insert ON {table}
                FOR INSERT
                WITH CHECK (true)
                """
            )
            continue

        op.execute(
            f"""
            CREATE POLICY role_visibility ON {table}
            USING ({predicate})
            WITH CHECK ({predicate})
            """
        )

    # applicant: ADMISSIONS_COUNSELOR sees only their own assigned
    # applicants; every other permitted role sees every applicant.
    applicant_predicate = (
        f"({_role_in(_ALL_APPLICANT_VISIBLE_ROLES)}) "
        f"OR ({_ACTOR_ROLE} = 'ADMISSIONS_COUNSELOR' AND assigned_counselor_id = {_ACTOR_ID})"
    )
    op.execute("ALTER TABLE applicant ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE applicant FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY role_visibility ON applicant
        USING ({applicant_predicate})
        WITH CHECK ({applicant_predicate})
        """
    )

    # application_status_event: visibility follows the parent applicant's
    # own visibility rule via a correlated subquery, rather than
    # duplicating a denormalized assigned_counselor_id onto every event row.
    event_predicate = f"""
        EXISTS (
            SELECT 1 FROM applicant a
            WHERE a.id = application_status_event.applicant_id
            AND (
                ({_role_in(_ALL_APPLICANT_VISIBLE_ROLES)})
                OR ({_ACTOR_ROLE} = 'ADMISSIONS_COUNSELOR' AND a.assigned_counselor_id = {_ACTOR_ID})
            )
        )
    """
    op.execute("ALTER TABLE application_status_event ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE application_status_event FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY role_visibility ON application_status_event
        USING ({event_predicate})
        WITH CHECK ({event_predicate})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_log_insert ON audit_log")
    op.execute("DROP POLICY IF EXISTS audit_log_select ON audit_log")
    op.execute("ALTER TABLE audit_log NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log DISABLE ROW LEVEL SECURITY")

    for table in (
        "application_status_event",
        "applicant",
        *(t for t in _ROLE_ONLY_POLICIES if t != "audit_log"),
    ):
        op.execute(f"DROP POLICY IF EXISTS role_visibility ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
