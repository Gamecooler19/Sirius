"""application_status_enum_rename

Revision ID: 0006_status_enum_rename
Revises: 0005_seed_roles
Create Date: 2026-09-22

Module 02 correction: the `ApplicationStatus` enum values chosen in Module
01 (`INQUIRY`, `APPLICATION_STARTED`, `DOCUMENTS_SUBMITTED`,
`UNDER_REVIEW`, `OFFER_MADE`, `ADMISSION_TAKEN`, `REJECTED`, `WITHDRAWN`)
drifted from the pipeline actually agreed for this project. This migration
replaces them with the correct set:

    IMPORTED -> APPLIED -> IN_PROCESS <-> ON_HOLD -> ADMISSION_OFFERED
    -> ADMISSION_TAKEN
    (REJECTED / WITHDRAWN reachable from APPLIED, IN_PROCESS, ON_HOLD, or
    ADMISSION_OFFERED; both terminal)

`IMPORTED` is the default status a freshly-imported applicant gets (Module
02's Excel-import endpoint inserts new `Applicant` rows at this status).
`ENROLLED` -- present in nobody's list, but worth stating explicitly since
a careless read of "the pipeline" might expect a stage after
`ADMISSION_TAKEN` -- is deliberately not part of this enum: out of scope
for now per the correction that introduced this migration.

**Why `ALTER TYPE ... RENAME VALUE` is not used here**, even though
Postgres 12+ supports it for a same-cardinality rename: this is not a pure
rename. `INQUIRY`/`APPLICATION_STARTED`/`DOCUMENTS_SUBMITTED`/
`UNDER_REVIEW`/`OFFER_MADE` (five old values) collapse and reorder into
`IMPORTED`/`APPLIED`/`IN_PROCESS`/`ON_HOLD`/`ADMISSION_OFFERED` (five new
values, but not a clean 1:1 semantic match -- `UNDER_REVIEW` had no
`ON_HOLD` counterpart in the old set at all, and the old set had no
`IN_PROCESS`/`ON_HOLD` back-and-forth pair). Recreating the type is the
correct tool for a genuine vocabulary change, not a rename; the standard
Postgres pattern for changing an enum column already storing production
data is: add a new type, swap the column to `text`, remap values, swap to
the new type, drop the old type. This module's own live verification
(this module's own report) confirmed the schema had zero rows in
`applicant`/`application_status_event` at the time this migration was
written, but the migration is written to be correct against a populated
table regardless -- an explicit `CASE` remapping, not an assumption that
the table is empty.

The mapping applied to any existing row (defensive; verified empty in this
environment, see the module-02 report):

    INQUIRY              -> IMPORTED
    APPLICATION_STARTED  -> APPLIED
    DOCUMENTS_SUBMITTED  -> IN_PROCESS
    UNDER_REVIEW         -> IN_PROCESS
    OFFER_MADE           -> ADMISSION_OFFERED
    ADMISSION_TAKEN      -> ADMISSION_TAKEN   (unchanged spelling)
    REJECTED             -> REJECTED          (unchanged spelling)
    WITHDRAWN            -> WITHDRAWN         (unchanged spelling)

`finance_record_requires_admission_taken()` is recreated verbatim --
`ADMISSION_TAKEN`'s spelling did not change between the old and new enum,
so the trigger's `'ADMISSION_TAKEN'` string-literal comparison needs no
edit, but the function is recreated here anyway (via `CREATE OR REPLACE`)
so this migration is self-contained and does not depend on assuming the
prior migration's function body is still exactly what is live -- the
column it reads (`applicant.current_status`) now has a different
underlying type (a freshly created `application_status` enum, same name,
different value set), and PL/pgSQL functions referencing a column's type
implicitly are revalidated at each call, not frozen at CREATE time, so this
step is not strictly required for correctness but is included for
auditability: a future reader of this migration should see the full,
current trigger body in the same diff that changed the type it depends on.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_status_enum_rename"
down_revision: str | None = "0005_seed_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_TO_NEW = {
    "INQUIRY": "IMPORTED",
    "APPLICATION_STARTED": "APPLIED",
    "DOCUMENTS_SUBMITTED": "IN_PROCESS",
    "UNDER_REVIEW": "IN_PROCESS",
    "OFFER_MADE": "ADMISSION_OFFERED",
    "ADMISSION_TAKEN": "ADMISSION_TAKEN",
    "REJECTED": "REJECTED",
    "WITHDRAWN": "WITHDRAWN",
}

NEW_TO_OLD = {
    "IMPORTED": "INQUIRY",
    "APPLIED": "APPLICATION_STARTED",
    # Both IN_PROCESS and ON_HOLD had no single old-value counterpart on
    # the way back down; ON_HOLD did not exist at all in the old set, and
    # IN_PROCESS's downgrade target is arbitrary (DOCUMENTS_SUBMITTED,
    # chosen as the earlier of its two old contributors) -- downgrade is a
    # best-effort compatibility path for local rollback, not a guarantee
    # of losslessness across a genuine vocabulary change in either
    # direction.
    "IN_PROCESS": "DOCUMENTS_SUBMITTED",
    "ON_HOLD": "UNDER_REVIEW",
    "ADMISSION_OFFERED": "OFFER_MADE",
    "ADMISSION_TAKEN": "ADMISSION_TAKEN",
    "REJECTED": "REJECTED",
    "WITHDRAWN": "WITHDRAWN",
}

OLD_VALUES = [
    "INQUIRY",
    "APPLICATION_STARTED",
    "DOCUMENTS_SUBMITTED",
    "UNDER_REVIEW",
    "OFFER_MADE",
    "ADMISSION_TAKEN",
    "REJECTED",
    "WITHDRAWN",
]

NEW_VALUES = [
    "IMPORTED",
    "APPLIED",
    "IN_PROCESS",
    "ON_HOLD",
    "ADMISSION_OFFERED",
    "ADMISSION_TAKEN",
    "REJECTED",
    "WITHDRAWN",
]

FINANCE_RECORD_GATE_FUNCTION = """
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


def _remap_column(table: str, column: str, mapping: dict[str, str]) -> None:
    """Swap `table.column` from the old `application_status` enum to
    `text`, remap every non-null value through `mapping`, drop the column's
    default (it referenced the old enum type and would otherwise dangle),
    ready for the caller to swap the type again once the new enum exists.
    """
    op.execute(f'ALTER TABLE "{table}" ALTER COLUMN {column} DROP DEFAULT')
    op.execute(f'ALTER TABLE "{table}" ALTER COLUMN {column} TYPE text USING {column}::text')
    case_expr = " ".join(f"WHEN '{old}' THEN '{new}'" for old, new in mapping.items())
    op.execute(
        f"""
        UPDATE "{table}"
        SET {column} = CASE {column} {case_expr} ELSE {column} END
        WHERE {column} IS NOT NULL
        """
    )


def upgrade() -> None:
    # 1. Drop the trigger that reads applicant.current_status as the old
    #    enum type -- it must not fire (and cannot type-check) while that
    #    column is temporarily `text` mid-migration.
    op.execute("DROP TRIGGER IF EXISTS finance_record_admission_gate ON finance_record")
    op.execute("DROP FUNCTION IF EXISTS finance_record_requires_admission_taken()")

    # 2. Swap every column using the old enum to text and remap values.
    _remap_column("applicant", "current_status", OLD_TO_NEW)
    _remap_column("application_status_event", "from_status", OLD_TO_NEW)
    _remap_column("application_status_event", "to_status", OLD_TO_NEW)

    # 3. Drop the old enum type, create the new one with the correct
    #    vocabulary and IMPORTED first (Postgres enum ordering has no
    #    runtime significance here -- comparisons are by value, not
    #    position -- but IMPORTED first documents it as the conceptual
    #    starting state).
    op.execute("DROP TYPE application_status")
    new_values_sql = ", ".join(f"'{v}'" for v in NEW_VALUES)
    op.execute(f"CREATE TYPE application_status AS ENUM ({new_values_sql})")

    # 4. Swap the columns back to the new enum type. applicant.current_status
    #    gets its default restored as IMPORTED -- module correction:
    #    "IMPORTED as the default status a freshly-imported applicant gets."
    op.execute(
        "ALTER TABLE applicant ALTER COLUMN current_status "
        "TYPE application_status USING current_status::application_status"
    )
    op.execute(
        "ALTER TABLE applicant ALTER COLUMN current_status SET DEFAULT 'IMPORTED'"
    )
    op.execute(
        "ALTER TABLE application_status_event ALTER COLUMN from_status "
        "TYPE application_status USING from_status::application_status"
    )
    op.execute(
        "ALTER TABLE application_status_event ALTER COLUMN to_status "
        "TYPE application_status USING to_status::application_status"
    )

    # 5. Recreate the trigger (see module docstring for why this is
    #    included even though ADMISSION_TAKEN's spelling did not change).
    op.execute(FINANCE_RECORD_GATE_FUNCTION)
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

    _remap_column("applicant", "current_status", NEW_TO_OLD)
    _remap_column("application_status_event", "from_status", NEW_TO_OLD)
    _remap_column("application_status_event", "to_status", NEW_TO_OLD)

    op.execute("DROP TYPE application_status")
    old_values_sql = ", ".join(f"'{v}'" for v in OLD_VALUES)
    op.execute(f"CREATE TYPE application_status AS ENUM ({old_values_sql})")

    op.execute(
        "ALTER TABLE applicant ALTER COLUMN current_status "
        "TYPE application_status USING current_status::application_status"
    )
    op.execute(
        "ALTER TABLE applicant ALTER COLUMN current_status SET DEFAULT 'INQUIRY'"
    )
    op.execute(
        "ALTER TABLE application_status_event ALTER COLUMN from_status "
        "TYPE application_status USING from_status::application_status"
    )
    op.execute(
        "ALTER TABLE application_status_event ALTER COLUMN to_status "
        "TYPE application_status USING to_status::application_status"
    )

    op.execute(FINANCE_RECORD_GATE_FUNCTION)
    op.execute(
        """
        CREATE TRIGGER finance_record_admission_gate
        BEFORE INSERT ON finance_record
        FOR EACH ROW EXECUTE FUNCTION finance_record_requires_admission_taken()
        """
    )
