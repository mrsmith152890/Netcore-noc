"""Replace map groups with direct domain assignment."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "c41a0b2d9e73"
down_revision: Union[str, Sequence[str], None] = "a92d4f6c1e7b"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("maps", sa.Column("domain_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_maps_domain_id_map_domains", "maps", "map_domains", ["domain_id"], ["id"], ondelete="SET NULL")
    op.execute(sa.text("""
        UPDATE maps
        SET domain_id = (
          SELECT map_groups.domain_id FROM map_groups WHERE map_groups.id = maps.group_id
        )
        WHERE group_id IS NOT NULL
    """))
    op.drop_constraint("fk_maps_group_id_map_groups", "maps", type_="foreignkey")
    op.drop_column("maps", "group_id")
    op.drop_table("map_groups")

def downgrade() -> None:
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
    op.execute(sa.text("""
        INSERT INTO map_groups (domain_id, name)
        SELECT DISTINCT domain_id, 'Sedes' FROM maps WHERE domain_id IS NOT NULL
    """))
    op.execute(sa.text("""
        UPDATE maps SET group_id = (
          SELECT map_groups.id FROM map_groups WHERE map_groups.domain_id = maps.domain_id
        ) WHERE domain_id IS NOT NULL
    """))
    op.drop_constraint("fk_maps_domain_id_map_domains", "maps", type_="foreignkey")
    op.drop_column("maps", "domain_id")
