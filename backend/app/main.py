from fastapi import FastAPI

from app.api.health import router as health_router
from app.config import settings

app = FastAPI(
    title=settings.app_name,
    description="AI-powered restaurant search and ordering agent",
    version=settings.app_version,
)

app.include_router(health_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} API is running", "docs": "/docs"}
