from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import BigInteger, Date, DateTime, Numeric, Text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    type_annotation_map = {  # noqa: RUF012
        int: BigInteger,
        str: Text,
        datetime: DateTime(timezone=True),
        date: Date,
        Decimal: Numeric(10, 2),
    }


def pg_enum(enum_cls: type[StrEnum], nombre: str) -> ENUM:
    """Tipo ENUM nativo ya creado por la migración (schema.sql); SQLAlchemy no lo crea ni lo borra."""
    return ENUM(enum_cls, name=nombre, create_type=False, values_callable=lambda e: [m.value for m in e])
