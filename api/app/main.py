"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import admin, auth, import_, status

settings = get_settings()

app = FastAPI(title="UnivAdmissions API")

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
app.include_router(import_.router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
