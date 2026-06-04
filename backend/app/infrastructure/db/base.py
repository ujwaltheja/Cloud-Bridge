"""
SQLAlchemy 2.0 Declarative Base for Cloud Bridge.

All models should inherit from this Base.
"""

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime, String, TypeDecorator


class GUID(TypeDecorator):
    """Platform-independent GUID/UUID type.

    - On PostgreSQL: uses native UUID type (as_uuid=True).
    - On SQLite (and others): stores as String(36) with dashed format.

    Always exposes uuid.UUID instances on the Python side.
    Defensively handles legacy "bad" data that may exist in SQLite DBs
    (e.g. integer values from accidental .int inserts, 32-char hex strings,
    or other string forms). This prevents "'int' object has no attribute 'replace'"
    errors when SQLAlchemy's UUID processor runs on result rows.
    """

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PGUUID

            return dialect.type_descriptor(PGUUID(as_uuid=True))
        else:
            # SQLite etc. — force TEXT storage
            return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid_lib.UUID):
            return str(value)
        # Accept strings (dashed, undashed 32-hex, etc.) and normalize
        try:
            return str(uuid_lib.UUID(str(value)))
        except Exception:
            # Last resort — store as-is and let higher layers complain
            return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid_lib.UUID):
            return value
        if isinstance(value, int):
            # Legacy bad data: a previous insert accidentally stored uuid.int (or SQLite
            # numeric affinity turned something into INTEGER). Reconstruct the UUID.
            try:
                return uuid_lib.UUID(int=value)
            except Exception:
                return value
        # str, bytes, memoryview, etc.
        try:
            v = str(value)
            if len(v) == 32 and "-" not in v:
                return uuid_lib.UUID(hex=v)
            return uuid_lib.UUID(v)
        except Exception:
            return value


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class TimestampMixin:
    """Mixin that provides created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
