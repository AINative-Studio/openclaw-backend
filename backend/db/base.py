"""
SQLAlchemy declarative base and database session configuration
"""
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from typing import Generator
import os
from dotenv import load_dotenv

# Load environment variables FIRST before reading DATABASE_URL
load_dotenv()

# Database URL from environment - PostgreSQL required
# Format: postgresql+asyncpg://user:password@host:port/database
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL environment variable is required. "
        "OpenClaw Backend requires PostgreSQL 14+ with asyncpg driver. "
        "Example: postgresql+asyncpg://postgres:password@localhost:5432/openclaw"
    )

# Create sync and async database URLs for PostgreSQL
# Sync uses psycopg2 (for migrations, seed scripts)
# Async uses asyncpg (for FastAPI endpoints)
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    # If asyncpg URL provided, create both sync (psycopg2) and async (asyncpg) versions
    SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    ASYNC_DATABASE_URL = DATABASE_URL
elif DATABASE_URL.startswith("postgresql://"):
    # If psycopg2 URL provided, use for sync and convert to asyncpg for async
    SYNC_DATABASE_URL = DATABASE_URL
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
else:
    raise ValueError(
        f"Invalid DATABASE_URL format: {DATABASE_URL[:20]}... "
        "Must start with 'postgresql://' or 'postgresql+asyncpg://'"
    )

# Create SQLAlchemy engines for PostgreSQL (sync and async)
engine = create_engine(
    SYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True  # Verify connections before using
)

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True  # Verify connections before using
)

# Create sessionmakers (sync and async)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Create declarative base
Base = declarative_base()


def get_db() -> Generator:
    """
    Database session dependency for FastAPI (synchronous)

    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db():
    """
    Async database session dependency for FastAPI

    Yields:
        Async database session
    """
    async with AsyncSessionLocal() as session:
        yield session


def init_db() -> None:
    """
    Initialize database by creating all tables

    ENFORCES: Railway PostgreSQL connection MUST work or app fails to start
    """
    print("🔒 ENFORCING Railway PostgreSQL Connection...")

    # TEST DATABASE CONNECTION - fail hard if unreachable
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        print(f"✅ Connected to Railway PostgreSQL: {engine.url.host}:{engine.url.port}/{engine.url.database}")
    except Exception as e:
        print(f"❌ FATAL: Cannot connect to Railway PostgreSQL database")
        print(f"   Host: {engine.url.host}")
        print(f"   Port: {engine.url.port}")
        print(f"   Database: {engine.url.database}")
        print(f"   Error: {str(e)}")
        print("")
        print("🚫 OpenClaw Backend REQUIRES Railway PostgreSQL connection")
        print("   The application will NOT start without it")
        raise SystemExit(1)

    # Create tables if needed
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables verified/created")
