"""Excel-import parsing, matching, and reconciliation logic.

Kept separate from `app.routers.import_.import_applicants` so the parsing/
matching rules (this file) are unit-testable independent of the FastAPI
request/response plumbing and the database session lifecycle (that file).
"""

import hashlib
import io
import re
from dataclasses import dataclass

from openpyxl import load_workbook

from app.core.field_limits import MAX_FIELD_LENGTH as _MAX_FIELD_LENGTH
from app.services.import_config import COLUMN_MAP


class MissingColumnsError(Exception):
    """Raised when the uploaded file's header row is missing one or more
    columns `app.services.import_config.COLUMN_MAP` expects. Carries the
    missing header names so the caller can build a 422 response naming
    them -- "a renamed header fails loudly instead of silently dropping
    data," per the module prompt.
    """

    def __init__(self, missing_headers: list[str]) -> None:
        self.missing_headers = missing_headers
        super().__init__(f"missing expected column(s): {', '.join(missing_headers)}")


@dataclass
class ParsedRow:
    row_number: int  # 1-based, matching the spreadsheet's own row numbers
    full_name: str
    email: str
    phone: str | None
    program: str
    intake_cycle: str


def compute_checksum(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def normalize_phone(raw: str | None) -> str | None:
    """Strips everything except digits, so `+91 98765-43210`,
    `9876543210`, and `(98765) 43210` all normalize to the same value for
    matching purposes. Returns `None` for an empty/whitespace-only input
    rather than an empty string, so a blank phone column never becomes a
    false match against another blank phone column -- matching code below
    treats `None` as "no phone to match on," never as a matchable value.
    """
    if raw is None:
        return None
    digits = re.sub(r"\D", "", raw)
    return digits or None


def normalize_email(raw: str | None) -> str | None:
    """Lowercased, stripped -- email matching should not depend on
    capitalization a data-entry human happened to use.
    """
    if raw is None:
        return None
    normalized = raw.strip().lower()
    return normalized or None


def parse_workbook(file_bytes: bytes) -> tuple[list[ParsedRow], list[str]]:
    """Returns `(parsed_rows, rejected_row_errors)`.

    Raises `MissingColumnsError` if the header row (row 1 of the active
    sheet) is missing any column `COLUMN_MAP` expects -- this check runs
    before any row is processed, so a renamed/missing header rejects the
    whole file rather than silently skipping the rows that needed it.

    A parsed row with a blank `full_name` or `email` (the two fields this
    module treats as mandatory for a usable applicant record) is not
    raised as an exception -- it is reported back as one entry in
    `rejected_row_errors`, naming the row number, so one malformed row does
    not abort an otherwise-good import of hundreds of rows. `program`/
    `intake_cycle` are database-`NOT NULL` but are defaulted to an empty
    string here rather than rejecting the row outright -- module scope
    does not specify these as reject-worthy, only `full_name`/`email` are
    treated as the load-bearing identity fields for matching.

    **A field exceeding `_MAX_FIELD_LENGTH` (255) is rejected the same
    way -- a real defect found and fixed live during this module's own
    follow-up verification, not a hypothetical.** `POST /applicants`
    (`app.schemas.applicant_create.ApplicantCreateRequest`) already
    bounds `full_name`/`program`/`intake_cycle`/`phone` to 255
    characters at the Pydantic layer, but this import path never goes
    through that schema at all -- it builds `Applicant(...)` ORM
    objects directly from this function's own `ParsedRow` dataclass,
    parsed straight out of the spreadsheet, so the schema fix protected
    exactly one of this application's two applicant-creation paths.
    Confirmed live: a real `.xlsx` with a genuine 5,000-character
    `Full Name` cell, uploaded through the real
    `POST /import/applicants`, was accepted with `created_count: 3,
    rejected_count: 0` and landed in the database in full (`SELECT
    length(full_name)` returned exactly `5000`) -- completely
    unguarded, exactly the same failure mode the manual-entry path
    already had before its own fix, on a path that fix never touched.
    Rejecting the row here, at parse time, mirrors this function's own
    existing missing-`full_name`/`email` handling exactly -- one bad
    row does not abort an otherwise-good import of hundreds of rows,
    and the caller gets a real, specific reason (naming the row number
    and which field) in `error_detail`/`rejected_count`, not a silent
    truncation or an opaque database error surfacing as a 500.
    """
    workbook = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    sheet = workbook.active
    if sheet is None:
        raise MissingColumnsError(list(COLUMN_MAP.values()))

    header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
    header_index: dict[str, int] = {}
    for idx, cell_value in enumerate(header_row):
        if cell_value is not None:
            header_index[str(cell_value).strip()] = idx

    missing = [
        expected_header
        for expected_header in COLUMN_MAP.values()
        if expected_header not in header_index
    ]
    if missing:
        raise MissingColumnsError(missing)

    parsed: list[ParsedRow] = []
    rejected: list[str] = []

    for row_number, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if row is None or all(cell is None for cell in row):
            continue  # a genuinely blank row, not a data row to reject

        def cell(logical_field: str) -> str | None:
            header = COLUMN_MAP[logical_field]
            idx = header_index[header]
            value = row[idx] if idx < len(row) else None
            return str(value).strip() if value is not None else None

        full_name = cell("full_name")
        email = cell("email")

        if not full_name or not email:
            rejected.append(
                f"row {row_number}: missing required field(s) "
                f"({'full_name' if not full_name else ''}"
                f"{' and ' if not full_name and not email else ''}"
                f"{'email' if not email else ''})"
            )
            continue

        phone = cell("phone")
        program = cell("program") or ""
        intake_cycle = cell("intake_cycle") or ""

        oversized_fields = [
            field_name
            for field_name, value in (
                ("full_name", full_name),
                ("email", email),
                ("phone", phone),
                ("program", program),
                ("intake_cycle", intake_cycle),
            )
            if value is not None and len(value) > _MAX_FIELD_LENGTH
        ]
        if oversized_fields:
            rejected.append(
                f"row {row_number}: field(s) exceed {_MAX_FIELD_LENGTH} characters "
                f"({', '.join(oversized_fields)})"
            )
            continue

        parsed.append(
            ParsedRow(
                row_number=row_number,
                full_name=full_name,
                email=email,
                phone=phone,
                program=program,
                intake_cycle=intake_cycle,
            )
        )

    return parsed, rejected
