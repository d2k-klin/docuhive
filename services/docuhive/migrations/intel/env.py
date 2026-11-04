"""Intelligence metadata only; scaffold owned by CL after OA bootstrap."""

from alembic import context
from docuhive.db import IntelBase, get_engine


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table":
        return name in IntelBase.metadata.tables
    return True


def run() -> None:
    if context.is_offline_mode():
        from docuhive.config.settings import get_settings

        context.configure(
            url=get_settings().database_url,
            literal_binds=True,
            target_metadata=IntelBase.metadata,
            version_table="alembic_version_intel",
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        with get_engine().connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=IntelBase.metadata,
                version_table="alembic_version_intel",
                include_object=include_object,
            )
            with context.begin_transaction():
                context.run_migrations()


run()
