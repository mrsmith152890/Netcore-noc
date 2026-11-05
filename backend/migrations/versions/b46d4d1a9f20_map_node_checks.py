"""Persist one-off ping and SNMP results on map nodes."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b46d4d1a9f20"
down_revision: Union[str, Sequence[str], None] = "a239eb7d7e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("map_nodes", sa.Column("last_ping_ok", sa.Boolean(), nullable=True))
    op.add_column("map_nodes", sa.Column("last_snmp_ok", sa.Boolean(), nullable=True))
    op.add_column("map_nodes", sa.Column("last_arp_seen", sa.Boolean(), nullable=True))
    op.add_column("map_nodes", sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column("map_nodes", "last_checked_at")
    op.drop_column("map_nodes", "last_arp_seen")
    op.drop_column("map_nodes", "last_snmp_ok")
    op.drop_column("map_nodes", "last_ping_ok")
