from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.base_class import Base
engine = create_engine(settings.DATABASE_URL, echo=True)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Async setup (for Bureau Scoring as per spec)
async_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
from sqlalchemy import pool
async_engine = create_async_engine(async_url, echo=True, poolclass=pool.NullPool)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession
)

async def get_async_db():
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()