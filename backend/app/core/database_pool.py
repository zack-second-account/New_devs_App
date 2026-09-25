from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging
from ..config import settings

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    async def initialize(self):
        """Initialize database connection pool"""
        if self.session_factory:
            return
        try:
            # - URL used supabase_db_* settings that do not exist; pool never started, every request served mock revenue.
            # - build from DATABASE_URL, the connection docker-compose configures.
            database_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

            # - QueuePool is sync only and rejects async engines.
            # - let the async engine pick its pool.
            self.engine = create_async_engine(
                database_url,
                pool_size=20,
                max_overflow=30,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False
            )

            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            logger.info("✅ Database connection pool initialized")

        except Exception as e:
            logger.error(f"❌ Database pool initialization failed: {e}")
            self.engine = None
            self.session_factory = None

    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()

    def get_session(self) -> AsyncSession:
        """Get database session from pool"""
        # - `async def` returned a coroutine, so `async with get_session()` failed.
        # - plain method.
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        return self.session_factory()

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session
