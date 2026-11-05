"""Add admin-controlled public login network summary toggle."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a92d4f6c1e7b"
down_revision: Union[str, Sequence[str], None] = "8abf23d91e30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_branding",
        sa.Column("login_status_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("app_branding", "login_status_enabled")
