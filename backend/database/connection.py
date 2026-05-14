"""
SmartRx AI — Database Connection & Session Management
Supports PostgreSQL (production) and SQLite (offline/demo)
"""

import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager
from typing import Generator
from pathlib import Path

# ─── Configuration ────────────────────────────────────────────

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    # Default: SQLite for offline/demo mode
    f"sqlite:///{Path(__file__).parent.parent}/smartrx_demo.db"
)

IS_SQLITE    = DATABASE_URL.startswith("sqlite")
IS_POSTGRES  = DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres")

# ─── Engine ───────────────────────────────────────────────────

def create_db_engine(url: str = DATABASE_URL):
    if IS_SQLITE:
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        # Enable WAL mode + foreign keys for SQLite
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()
        return engine

    # PostgreSQL
    return create_engine(
        url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,      # detect stale connections
        pool_recycle=3600,
        echo=False,
    )

engine       = create_db_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# ─── Dependency (FastAPI) ─────────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for scripts and background tasks."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# ─── Init ─────────────────────────────────────────────────────

def init_db():
    """Create all tables. Safe to call multiple times."""
    from backend.models.models import Base
    Base.metadata.create_all(bind=engine)
    print(f"✅ Database initialised → {DATABASE_URL[:60]}...")

def drop_db():
    """Drop all tables — use only in dev/test."""
    from backend.models.models import Base
    Base.metadata.drop_all(bind=engine)
    print("⚠️  All tables dropped.")

def check_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"❌ DB connection failed: {e}")
        return False
