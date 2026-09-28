"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import (
    admin,
    applicant_create,
    applicants_read,
    auth,
    finance_record,
    import_,
    import_batches_read,
    notifications,
    payment_claim,
    reconciliation,
    status,
    users,
)

settings = get_settings()

app = FastAPI(title="Sirius API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(status.router)
app.include_router(applicant_create.router)
app.include_router(import_.router)
app.include_router(payment_claim.router)
app.include_router(finance_record.router)
app.include_router(applicants_read.router)
app.include_router(import_batches_read.router)
app.include_router(reconciliation.router)
app.include_router(users.router)
app.include_router(notifications.router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
