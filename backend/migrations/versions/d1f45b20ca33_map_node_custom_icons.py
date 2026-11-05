"""Allow custom names and images on map nodes."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d1f45b20ca33"
down_revision: Union[str, Sequence[str], None] = "c96d40e8f2a1"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("map_nodes", sa.Column("icon_data", sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column("map_nodes", "icon_data")
