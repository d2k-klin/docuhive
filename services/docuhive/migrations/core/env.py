"""Core metadata only; intelligence tables are excluded from autogeneration."""

from alembic import context
from docuhive.db import (
    CoreBase,
    get_engine,
    models,  # noqa: F401
)


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table":
        return name in CoreBase.metadata.tables
    return True


def run() -> None:
    if context.is_offline_mode():
        from docuhive.config.settings import get_settings

        context.configure(
            url=get_settings().database_url,
            literal_binds=True,
            target_metadata=CoreBase.metadata,
            version_table="alembic_version_core",
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        with get_engine().connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=CoreBase.metadata,
                version_table="alembic_version_core",
                include_object=include_object,
            )
            with context.begin_transaction():
                context.run_migrations()


run()
