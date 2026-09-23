"""import_batch_counts_and_checksum

Revision ID: 0008_import_batch_counts
Revises: 0007_finance_record_auto_create
Create Date: 2026-09-23

Extends `import_batch` (Module 01's table-only scaffold) with what the
Excel-import endpoint actually needs to report and to dedupe against:

- `checksum`: sha256 hex digest of the uploaded file's raw bytes. The
  import endpoint looks up any prior `import_batch` row with the same
  checksum and a `COMPLETED` status before processing anything, and
  short-circuits as a no-op (returns that prior batch's own counts,
  touches zero rows) if one exists -- "computes a checksum and
  short-circuits as a no-op if that exact file was already imported," per
  the module prompt. Not a unique constraint: a `FAILED` batch for the
  same checksum should not block a genuine retry of the same file after
  whatever caused the failure is fixed, so the lookup is scoped to
  `status = 'COMPLETED'` in application code, not enforced as a database
  uniqueness invariant.
- `created_count` / `updated_count` / `flagged_count` / `rejected_count`:
  one column per outcome a row can have, so "the person who ran it can
  actually see" a breakdown rather than only a single `row_count` total
  (which Module 01 already had and this migration keeps, unchanged, as
  the sum of all four).
- `flagged_rows`: JSONB array of `{row_number, applicant_id, email, phone,
  reason}` objects -- one entry per row this import flagged for manual
  review (a match whose email or phone changed; see the import endpoint's
  own docstring) rather than a separate table. A JSONB column on the batch
  row itself is proportionate here: there is no review-resolution workflow
  in this module (explicitly deferred), so the only consumer of this data
  is a human reading the batch's own summary, not a query joining across
  many batches' flagged rows -- a dedicated table would be the right call
  the moment a future module adds a "resolve this flag" action, not before.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008_import_batch_counts"
down_revision: str | None = "0007_finance_record_auto_create"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("import_batch", sa.Column("checksum", sa.String(), nullable=True))
    op.add_column(
        "import_batch",
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "import_batch",
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "import_batch",
        sa.Column("flagged_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "import_batch",
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "import_batch",
        sa.Column(
            "flagged_rows", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.create_index("ix_import_batch_checksum", "import_batch", ["checksum"])


def downgrade() -> None:
    op.drop_index("ix_import_batch_checksum", table_name="import_batch")
    op.drop_column("import_batch", "flagged_rows")
    op.drop_column("import_batch", "rejected_count")
    op.drop_column("import_batch", "flagged_count")
    op.drop_column("import_batch", "updated_count")
    op.drop_column("import_batch", "created_count")
    op.drop_column("import_batch", "checksum")
