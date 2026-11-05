"""Allow maps to belong to multiple domains."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d7a421b95f6c"
down_revision: Union[str, Sequence[str], None] = "c41a0b2d9e73"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "map_domain_maps",
        sa.Column("map_id", sa.Integer(), sa.ForeignKey("maps.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("domain_id", sa.Integer(), sa.ForeignKey("map_domains.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(sa.text("""
        INSERT INTO map_domain_maps (map_id, domain_id)
        SELECT id, domain_id FROM maps WHERE domain_id IS NOT NULL
    """))
    op.drop_constraint("fk_maps_domain_id_map_domains", "maps", type_="foreignkey")
    op.drop_column("maps", "domain_id")

def downgrade() -> None:
    op.add_column("maps", sa.Column("domain_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_maps_domain_id_map_domains", "maps", "map_domains", ["domain_id"], ["id"], ondelete="SET NULL")
    op.execute(sa.text("""
        UPDATE maps SET domain_id = (
          SELECT MIN(map_domain_maps.domain_id) FROM map_domain_maps WHERE map_domain_maps.map_id = maps.id
        )
    """))
    op.drop_table("map_domain_maps")
