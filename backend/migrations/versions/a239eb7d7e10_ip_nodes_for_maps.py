"""IP nodes for maps and one-shot router discovery."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a239eb7d7e10"
down_revision: Union[str, Sequence[str], None] = "861c58b659cb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("map_nodes", sa.Column("ip_address", sa.String(length=45), nullable=True))
    op.add_column("map_nodes", sa.Column("discovery_source", sa.String(length=20), nullable=True))
    op.create_unique_constraint("uq_map_node_ip", "map_nodes", ["map_id", "ip_address"])

def downgrade() -> None:
    op.drop_constraint("uq_map_node_ip", "map_nodes", type_="unique")
    op.drop_column("map_nodes", "discovery_source")
    op.drop_column("map_nodes", "ip_address")
