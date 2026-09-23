"""Column mapping configuration for the Excel-import endpoint.

A plain, versioned Python dict rather than a database-editable settings
table -- this module has no admin UI for editing import configuration, so
"stored config" here means "one reviewed, single source of truth the
parsing code reads," not yet "editable at runtime without a deploy." A
future module adding an admin screen for this can move `COLUMN_MAP` into a
database table and change only `app.services.excel_import`'s lookup, not
every call site, since the parsing code already treats this dict as the
one place header names are decided.

**Why this exists at all, instead of hardcoding `row["Full Name"]` inline
in the parsing loop.** The module prompt is explicit: "maps columns
through a stored config rather than hardcoded column names so a renamed
header fails loudly instead of silently dropping data." Hardcoding the
literal header string at each field-access site means a renamed column
("Full Name" -> "Applicant Name" in a future term's template) produces a
`KeyError`/`None` at the point of use, potentially for only *some* fields
if the rename is partial across sheets -- silent, partial data loss.
Centralizing the map here means header validation
(`app.services.excel_import.validate_headers`) checks every expected
header exists *before* processing a single row, and rejects the whole
file loudly (422, naming the missing header) if not.
"""

# Logical field name -> the exact header text expected in row 1 of the
# uploaded .xlsx. Case-sensitive, exact match (no fuzzy header matching --
# an inexact match is exactly the kind of "silently accept something
# close enough" behavior the module prompt's "fails loudly" requirement
# rules out).
COLUMN_MAP: dict[str, str] = {
    "full_name": "Full Name",
    "email": "Email",
    "phone": "Phone",
    "program": "Program",
    "intake_cycle": "Intake Cycle",
}

REQUIRED_LOGICAL_FIELDS = frozenset(COLUMN_MAP.keys())
