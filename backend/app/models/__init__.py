# Import every model here so `Base.metadata` knows about all tables.
# Alembic's autogenerate imports this package to compare models vs database.
from app.models.user import User

__all__ = ["User"]
