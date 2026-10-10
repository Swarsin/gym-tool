from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

# We expect a Supabase Postgres connection string in the environment
# Example: postgresql+asyncpg://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT].supabase.co:5432/postgres
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres")

# Create the async engine with safe pool limits for Supabase
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_size=3,
    max_overflow=2,
    pool_timeout=10,
    pool_pre_ping=True,
    pool_recycle=300
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

async def get_db() -> AsyncSession:
    """
    Dependency to yield an async database session for FastAPI endpoints.
    """
    async with AsyncSessionLocal() as session:
        yield session
