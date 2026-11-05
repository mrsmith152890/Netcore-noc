"""Add persistent application branding settings."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "8abf23d91e30"
down_revision: Union[str, Sequence[str], None] = "f31c2a9d65b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_branding",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("logo_data", sa.Text(), nullable=True),
        sa.Column("favicon_data", sa.Text(), nullable=True),
        sa.Column("login_art_data", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_branding")
