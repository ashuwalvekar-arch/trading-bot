"""
Utility script: create all database tables.
Usage:
    python create_db.py
"""
import asyncio
from database.db import init_db

if __name__ == "__main__":
    asyncio.run(init_db())
    print("DATABASE CREATED")
