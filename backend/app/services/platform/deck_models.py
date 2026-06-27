from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DeckRow(Base):
    __tablename__ = "decks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(500))
    deck_type: Mapped[str] = mapped_column(String(64))
    theme: Mapped[str] = mapped_column(String(64))
    aspect_ratio: Mapped[str] = mapped_column(String(16))
    generation_payload: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    current_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "deck_versions.id",
            name="fk_decks_current_version_id_deck_versions",
            use_alter=True,
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        index=True,
    )


class DeckVersionRow(Base):
    __tablename__ = "deck_versions"
    __table_args__ = (
        UniqueConstraint(
            "deck_id",
            "version_number",
            name="uq_deck_versions_deck_id_version_number",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    deck_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("decks.id", ondelete="CASCADE"),
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(32))
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
