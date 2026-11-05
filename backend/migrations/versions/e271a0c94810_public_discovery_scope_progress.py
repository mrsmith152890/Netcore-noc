"""Authorize public VPN ranges per scope and report scan progress."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "e271a0c94810"
down_revision: Union[str, Sequence[str], None] = "d1f45b20ca33"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("discovery_scopes", sa.Column("allow_public", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("discovery_runs", sa.Column("hosts_scanned", sa.Integer(), server_default="0", nullable=False))

def downgrade() -> None:
    op.drop_column("discovery_runs", "hosts_scanned")
    op.drop_column("discovery_scopes", "allow_public")
