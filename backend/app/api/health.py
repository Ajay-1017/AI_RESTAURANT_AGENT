from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check: is the process up and serving requests?

    Deliberately does NOT touch the database or any external service.
    A readiness check that pings PostgreSQL is added in Phase 2.
    """
    return {"status": "ok"}
