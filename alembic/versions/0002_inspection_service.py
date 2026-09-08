"""Add 验货宝 inspection service fields.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE inspectionfilter AS ENUM
                ('ANY', 'WITH_INSPECTION', 'MANDATORY_INSPECTION', 'WITHOUT_INSPECTION');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
        """
    )
    op.execute(
        "ALTER TABLE search_tasks ADD COLUMN IF NOT EXISTS inspection_filter "
        "inspectionfilter NOT NULL DEFAULT 'ANY'"
    )
    op.execute(
        "ALTER TABLE items ADD COLUMN IF NOT EXISTS inspection_service_available "
        "BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE items ADD COLUMN IF NOT EXISTS inspection_service_mandatory "
        "BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS inspection_service_type VARCHAR(64)")
    op.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS inspection_service_version VARCHAR(32)")
    op.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS inspection_service_description TEXT")
    op.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS inspection_service_url TEXT")
    op.execute(
        "ALTER TABLE items ADD COLUMN IF NOT EXISTS inspection_service_raw "
        "JSONB NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE items DROP COLUMN IF EXISTS inspection_service_raw")
    op.execute("ALTER TABLE items DROP COLUMN IF EXISTS inspection_service_url")
    op.execute("ALTER TABLE items DROP COLUMN IF EXISTS inspection_service_description")
    op.execute("ALTER TABLE items DROP COLUMN IF EXISTS inspection_service_version")
    op.execute("ALTER TABLE items DROP COLUMN IF EXISTS inspection_service_type")
    op.execute("ALTER TABLE items DROP COLUMN IF EXISTS inspection_service_mandatory")
    op.execute("ALTER TABLE items DROP COLUMN IF EXISTS inspection_service_available")
    op.execute("ALTER TABLE search_tasks DROP COLUMN IF EXISTS inspection_filter")
    op.execute("DROP TYPE IF EXISTS inspectionfilter")
