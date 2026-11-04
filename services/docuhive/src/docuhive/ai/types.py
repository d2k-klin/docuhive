"""Column types for intel tables: Postgres types in production, portable ones in SQLite tests."""

from sqlalchemy import JSON, BigInteger, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

Json = JSON().with_variant(JSONB(), "postgresql")
TextArray = JSON().with_variant(ARRAY(Text), "postgresql")
# bigserial in Postgres; SQLite only autoincrements INTEGER PRIMARY KEY.
BigId = BigInteger().with_variant(Integer(), "sqlite")


def vector(dims: int):  # type: ignore[no-untyped-def]
    from pgvector.sqlalchemy import Vector

    return JSON().with_variant(Vector(dims), "postgresql")
