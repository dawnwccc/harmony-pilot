import asyncio

from sqlalchemy import event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config.schema import DBConfig
from core.logger.runtime import get_logger

logger = get_logger(name="Sesseion Manager")


# https://github.com/Pythagora-io/gpt-pilot/blob/main/core/db/session.py
class SessionManager:
    """
    Async-aware context manager for database session.

    Usage:
    >>> config = DBConfig(url="sqlite+aiosqlite:///test.db")
    >>> async with SessionManager(config) as session:
    ...     # Do something with the session
    """

    def __init__(self, config: DBConfig):
        """
        Initialize the session manager with the given configuration.

        :param config: Database configuration.
        """
        self.config = config
        self.async_engine = create_async_engine(
            self.config.url, echo=config.debug_sql, echo_pool="debug" if config.debug_sql else None
        )
        self.AsyncSessionClass = async_sessionmaker(self.async_engine, expire_on_commit=False)
        self.async_session = None

        self.recursion_depth = 0

        event.listen(self.async_engine.sync_engine, "connect", self._on_connect)

    def _on_connect(self, dbapi_connection, _):
        """Connection event handler"""
        logger.debug(f"Connected to database {self.config.url}")

        if self.config.url.startswith("sqlite"):
            # Note that SQLite uses NullPool by default, meaning every session creates a
            # database "connection". This is fine and preferred for SQLite because
            # it's a local file. PostgreSQL or other database use a real connection pool
            # by default.
            dbapi_connection.execute("pragma foreign_keys=on")

    async def async_start(self) -> AsyncSession:
        if self.async_session is not None:
            self.recursion_depth += 1
            logger.warning(f"Re-entering database session (depth: {self.recursion_depth}), potential bug", stack_info=True)
            return self.async_session

        self.async_session = self.AsyncSessionClass()
        return self.async_session

    async def async_close(self):
        if self.async_session is None:
            logger.warning("Closing database session that was never opened", stack_info=True)
            return
        if self.recursion_depth > 0:
            self.recursion_depth -= 1
            return

        await self.async_session.close()
        self.async_session = None

    async def __aenter__(self) -> AsyncSession:
        return await self.async_start()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.async_close()


__all__ = ["SessionManager"]
