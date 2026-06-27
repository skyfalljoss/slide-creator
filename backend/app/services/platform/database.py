from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.platform.deck_models import Base
from app.services.platform.sqlite import enable_sqlite_foreign_keys, prepare_sqlite_database


class Database:
    def __init__(self, url: str) -> None:
        prepare_sqlite_database(url)
        self.engine = create_async_engine(url)
        enable_sqlite_foreign_keys(self.engine)
        self._session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def create_schema(self) -> None:
        """Create all tables for isolated tests; production uses Alembic."""
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
