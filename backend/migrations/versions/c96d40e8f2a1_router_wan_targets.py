"""Add optional WAN targets and latest probe status for routers."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "c96d40e8f2a1"
down_revision: Union[str, Sequence[str], None] = "b46d4d1a9f20"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("devices", sa.Column("wan_gateway_ip", sa.String(length=45), nullable=True))
    op.add_column("devices", sa.Column("wan_probe_ip", sa.String(length=45), nullable=True))
    op.add_column("device_status", sa.Column("wan_gateway_state", sa.String(length=10), nullable=True))
    op.add_column("device_status", sa.Column("wan_gateway_rtt_ms", sa.Float(), nullable=True))
    op.add_column("device_status", sa.Column("wan_probe_state", sa.String(length=10), nullable=True))
    op.add_column("device_status", sa.Column("wan_probe_rtt_ms", sa.Float(), nullable=True))
    op.add_column("device_status", sa.Column("wan_checked_at", sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column("device_status", "wan_checked_at")
    op.drop_column("device_status", "wan_probe_rtt_ms")
    op.drop_column("device_status", "wan_probe_state")
    op.drop_column("device_status", "wan_gateway_rtt_ms")
    op.drop_column("device_status", "wan_gateway_state")
    op.drop_column("devices", "wan_probe_ip")
    op.drop_column("devices", "wan_gateway_ip")
