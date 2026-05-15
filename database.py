"""
Root-level database shim.
Delegates to the proper async engine defined in database/db.py.
Kept for backward compatibility with create_db.py and any legacy imports.
"""
from database.db import engine, AsyncSessionLocal, init_db, get_session
from database.models import Base

__all__ = ["engine", "AsyncSessionLocal", "init_db", "get_session", "Base"]
