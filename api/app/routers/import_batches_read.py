"""Read-only list endpoint over `import_batch` (Module 02's Excel-import
table), giving the people who actually run imports a way to see their own
batch history and outcome counts without needing to remember each batch's
id.

**RBAC.** `SUPER_ADMIN`, `ADMISSIONS_MANAGER`, `AUDITOR` -- the exact same
three roles `import_batch`'s own `role_visibility` RLS policy already
scopes this table to (see Module 02's report and this table's own
migration). Enforced explicitly at the application layer here for the
same reason `payment_claim`'s list endpoint enforces its own allowlist
explicitly rather than leaning on RLS alone for a *list* route: a role
outside this set gets a clean 403, not a 200 with an empty `items` list
indistinguishable from "nothing to see yet."
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role_session
from app.models.enums import RoleCode
from app.models.import_batch import ImportBatch
from app.models.user import User
from app.schemas.reads import ImportBatchListResponse, ImportBatchSummary

router = APIRouter(prefix="/import-batches", tags=["reads"])

_LIST_ROLES = (RoleCode.SUPER_ADMIN, RoleCode.ADMISSIONS_MANAGER, RoleCode.AUDITOR)


@router.get("", response_model=ImportBatchListResponse)
async def list_import_batches(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_and_db: tuple[User, AsyncSession] = Depends(require_role_session(*_LIST_ROLES)),
) -> ImportBatchListResponse:
    _, db = user_and_db

    total = (await db.execute(select(func.count()).select_from(ImportBatch))).scalar_one()

    result = await db.execute(
        select(ImportBatch)
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.scalars().all()

    return ImportBatchListResponse(
        items=[
            ImportBatchSummary(
                id=b.id,
                source_filename=b.source_filename,
                status=b.status.value,
                row_count=b.row_count,
                checksum=b.checksum,
                created_count=b.created_count,
                updated_count=b.updated_count,
                flagged_count=b.flagged_count,
                rejected_count=b.rejected_count,
                error_detail=b.error_detail,
                imported_by=b.imported_by,
                created_at=b.created_at,
                completed_at=b.completed_at,
            )
            for b in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
