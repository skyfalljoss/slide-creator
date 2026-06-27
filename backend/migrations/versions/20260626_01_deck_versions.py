"""Add versioned deck tables.

Revision ID: 20260626_01
Revises:
Create Date: 2026-06-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260626_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("deck_type", sa.String(length=64), nullable=False),
        sa.Column("theme", sa.String(length=64), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=16), nullable=False),
        sa.Column("generation_payload", sa.JSON(), nullable=True),
        sa.Column("current_version_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_decks_owner_id"), "decks", ["owner_id"], unique=False)
    op.create_index(op.f("ix_decks_updated_at"), "decks", ["updated_at"], unique=False)

    op.create_table(
        "deck_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deck_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["deck_id"], ["decks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
        sa.UniqueConstraint(
            "deck_id",
            "version_number",
            name="uq_deck_versions_deck_id_version_number",
        ),
    )
    op.create_index(op.f("ix_deck_versions_deck_id"), "deck_versions", ["deck_id"], unique=False)

    with op.batch_alter_table("decks") as batch_op:
        batch_op.create_foreign_key(
            "fk_decks_current_version_id_deck_versions",
            "deck_versions",
            ["current_version_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("decks") as batch_op:
        batch_op.drop_constraint(
            "fk_decks_current_version_id_deck_versions",
            type_="foreignkey",
        )

    op.drop_index(op.f("ix_deck_versions_deck_id"), table_name="deck_versions")
    op.drop_table("deck_versions")
    op.drop_index(op.f("ix_decks_updated_at"), table_name="decks")
    op.drop_index(op.f("ix_decks_owner_id"), table_name="decks")
    op.drop_table("decks")
