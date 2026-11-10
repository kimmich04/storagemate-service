"""Base SQLAlchemy dùng chung + quy ước đặt tên index/constraint (để Alembic sinh tên ổn định).

Model của từng domain nằm trong <domain>/models.py và kế thừa Base ở đây.
type_annotation_map khớp kiểu của migration 0001_init: id bigint, chữ text, thời điểm timestamptz.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, MetaData, Text
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        int: BigInteger,
        str: Text,
        datetime: DateTime(timezone=True),
    }
