from __future__ import annotations

from fastapi import FastAPI

from app.config import settings
from app.db import connect, database_driver
from app.routes.admin import router as admin_router
from app.routes.console import router as console_router
from app.routes.public import router as public_router


app = FastAPI(title=settings.app_name)


@app.get("/health")
def health():
    db_ready = False
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
        db_ready = True
    except Exception:
        db_ready = False
    return {
        "ok": db_ready,
        "service": settings.app_name,
        "env": settings.env,
        "database": {
            "driver": database_driver(),
            "ready": db_ready,
        },
    }


app.include_router(public_router, prefix=settings.api_prefix)
app.include_router(admin_router, prefix=settings.api_prefix)
app.include_router(console_router)
