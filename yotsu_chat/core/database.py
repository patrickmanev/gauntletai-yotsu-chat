import aiosqlite
import os
from typing import AsyncGenerator
from pathlib import Path

# We only care about TEST_MODE - everything else is DEV by default
TEST_MODE = os.getenv("TEST_MODE", "0") == "1"
print(f"[DEBUG] Database - TEST_MODE: {TEST_MODE}")

# Database paths with explicit Windows path handling
DB_ROOT = Path("data/db").resolve()
TEST_DB_PATH = (DB_ROOT / "test" / "test_yotsu_chat.db").resolve()
DEV_DB_PATH = (DB_ROOT / "dev" / "dev_yotsu_chat.db").resolve()

# Set the database path - only two options
DATABASE_URL = str(TEST_DB_PATH if TEST_MODE else DEV_DB_PATH)
print(f"[DEBUG] Database - Using {'TEST' if TEST_MODE else 'DEV'} database at: {DATABASE_URL}")

# Ensure database directories exist
DB_ROOT.mkdir(parents=True, exist_ok=True)
TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DEV_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def validate_database_operation():
    """Validate that we're operating on the correct database"""
    current_db = Path(DATABASE_URL).resolve()
    
    # The only validation we need is to prevent test operations on dev database
    if TEST_MODE and current_db != TEST_DB_PATH:
        raise RuntimeError(f"TEST_MODE operations attempted on development database: {current_db}")

async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Get database connection with proper mode validation"""
    validate_database_operation()
    print(f"[DEBUG] Database - Opening connection to: {DATABASE_URL}")
    db = await aiosqlite.connect(DATABASE_URL)
    try:
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row
        yield db
    finally:
        await db.close()
        print(f"[DEBUG] Database - Closed connection to: {DATABASE_URL}")

async def init_db(force: bool = False):
    """Initialize the database with all required tables."""
    print(f"[DEBUG] Database - Initializing database at: {DATABASE_URL}")
    print(f"[DEBUG] Database - Mode: {'TEST' if TEST_MODE else 'DEV'}")
    
    # Extra validation for database operations
    validate_database_operation()
    
    # In TEST_MODE, we always drop tables
    # In DEV_MODE, we only drop if force=True
    should_drop = TEST_MODE or force
    
    if should_drop and not TEST_MODE:
        print("[WARNING] Forced table drop requested on DEV database!")
    
    print(f"[DEBUG] Database - Should drop tables: {should_drop}")
    
    async with aiosqlite.connect(DATABASE_URL) as db:
        try:
            await db.execute("PRAGMA foreign_keys = ON")
            
            if should_drop:
                print(f"[DEBUG] Database - Dropping all tables")
                # Drop existing tables in reverse order of dependencies
                await db.execute("DROP TABLE IF EXISTS reactions")
                await db.execute("DROP TABLE IF EXISTS attachments")
                await db.execute("DROP TABLE IF EXISTS messages")
                await db.execute("DROP TABLE IF EXISTS channels_members")
                await db.execute("DROP TABLE IF EXISTS channels")
                await db.execute("DROP TABLE IF EXISTS users")
            
            print(f"[DEBUG] Database - Creating tables if they don't exist")
            
            # Create users table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    totp_secret TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create channels table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL CHECK (type IN ('public', 'private')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create channels_members table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS channels_members (
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    PRIMARY KEY (channel_id, user_id)
                )
            """)
            
            # Create messages table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    edited_at TIMESTAMP,
                    parent_id INTEGER,
                    FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (parent_id) REFERENCES messages(message_id) ON DELETE CASCADE
                )
            """)
            
            # Create attachments table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS attachments (
                    attachment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER,
                    filename TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    mime_type TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
                )
            """)
            
            # Create reactions table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reactions (
                    reaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    emoji TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    UNIQUE(message_id, user_id, emoji)
                )
            """)
            
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise e 