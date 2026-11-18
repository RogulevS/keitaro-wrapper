"""initial tables

Revision ID: 001_initial
Revises:
Create Date: 2026-11-18
"""

from alembic import op
import sqlalchemy as sa

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tracker_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("base_url", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("api_key", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("domain_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "local_campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keitaro_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("alias", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("country_codes", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("domain_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_local_campaigns_keitaro_id", "local_campaigns", ["keitaro_id"], unique=True)
    op.create_table(
        "local_streams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("local_campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keitaro_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("stream_type", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("schema_name", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tracks_offers", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_dirty", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("campaign_id", "keitaro_id", name="uq_stream_remote"),
    )
    op.create_index("ix_local_streams_keitaro_id", "local_streams", ["keitaro_id"])
    op.create_table(
        "stream_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stream_id", sa.Integer(), sa.ForeignKey("local_streams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keitaro_offer_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("share", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("draft_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("published_share", sa.Integer(), nullable=True),
        sa.Column("published_status", sa.String(length=16), nullable=True),
        sa.Column("published_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("stream_id", "keitaro_offer_id", name="uq_stream_offer"),
    )
    op.create_index("ix_stream_offers_keitaro_offer_id", "stream_offers", ["keitaro_offer_id"])


def downgrade() -> None:
    op.drop_table("stream_offers")
    op.drop_table("local_streams")
    op.drop_index("ix_local_campaigns_keitaro_id", table_name="local_campaigns")
    op.drop_table("local_campaigns")
    op.drop_table("tracker_settings")
