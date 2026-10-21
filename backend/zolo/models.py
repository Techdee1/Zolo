"""Import every model so Alembic and `Base.metadata` see all tables."""

from zolo.core.base import Base

__all__ = ["Base"]
