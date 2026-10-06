import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check: is the process up and serving requests?

    Deliberately does NOT touch the database or any external service.
    """
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    """Readiness check: can this instance serve real traffic right now?"""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # Log details server-side; never send internal errors to the client.
        logger.warning("Readiness check failed: database unreachable", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )
    return {"status": "ready", "database": "ok"}
