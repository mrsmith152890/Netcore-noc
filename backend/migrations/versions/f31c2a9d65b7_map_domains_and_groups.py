"""Add map domains and groups."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "f31c2a9d65b7"
down_revision: Union[str, Sequence[str], None] = "e271a0c94810"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "map_domains",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "map_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("domain_id", sa.Integer(), sa.ForeignKey("map_domains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("domain_id", "name", name="uq_map_group_domain_name"),
    )
    op.add_column("maps", sa.Column("group_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_maps_group_id_map_groups", "maps", "map_groups", ["group_id"], ["id"], ondelete="SET NULL")

def downgrade() -> None:
    op.drop_constraint("fk_maps_group_id_map_groups", "maps", type_="foreignkey")
    op.drop_column("maps", "group_id")
    op.drop_table("map_groups")
    op.drop_table("map_domains")
