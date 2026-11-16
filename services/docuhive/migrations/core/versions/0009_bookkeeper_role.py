"""The bookkeeper role: a member who may also see the categories assigned to bookkeepers."""

from alembic import op

revision = "0009_bookkeeper_role"
down_revision = "0008_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_role_check "
        "CHECK (role IN ('admin', 'member', 'bookkeeper'))"
    )


def downgrade() -> None:
    op.execute("UPDATE users SET role = 'member' WHERE role = 'bookkeeper'")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('admin', 'member'))"
    )
