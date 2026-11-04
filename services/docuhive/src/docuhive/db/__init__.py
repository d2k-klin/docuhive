"""SQLAlchemy bases and transactional sessions; intelligence metadata is separate."""

from collections.abc import Iterator
from contextlib import AbstractContextManager as ContextManager
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from docuhive.config.settings import get_settings


class CoreBase(DeclarativeBase):
    pass


class IntelBase(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@contextmanager
def _transaction() -> Iterator[Session]:
    with Session(get_engine()) as db:
        with db.begin():
            yield db


def session() -> ContextManager[Session]:
    return _transaction()
