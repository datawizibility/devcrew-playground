"""tenancy rls

Revision ID: 0001
Revises:
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TENANT_POLICY = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'smartap_app') THEN
        CREATE ROLE smartap_app LOGIN;
    END IF;
END
$$;
"""

# Deviation: the docker postgres image bootstraps `smartap` as a superuser,
# and superusers always bypass RLS even with FORCE ROW LEVEL SECURITY. Demote
# it (createdb/createrole attributes are retained) so the owner connection
# used by dev/tests is actually subject to the tenant_isolation policy.
DEMOTE_SMARTAP = """
DO $demote$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'smartap' AND rolsuper
    ) THEN
        ALTER ROLE smartap NOSUPERUSER;
    END IF;
END
$demote$;
"""


def upgrade() -> None:
    op.execute(TENANT_POLICY)

    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    # Row-level security on users
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON users USING "
        "(tenant_id = current_setting('app.tenant_id', true)::uuid)"
    )
    op.execute("GRANT USAGE ON SCHEMA public TO smartap_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO smartap_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO smartap_app")

    # Must run last: everything above still needs superuser privileges.
    op.execute(DEMOTE_SMARTAP)


def downgrade() -> None:
    op.drop_table("users")
    op.drop_table("tenants")