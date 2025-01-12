import aiosqlite
from datetime import datetime
from typing import AsyncGenerator
from pathlib import Path
import asyncio
import logging
import os

from .config import get_settings, EnvironmentMode
from ..utils import debug_log

logger = logging.getLogger(__name__)

# Get settings instance
settings = get_settings()

def validate_path(path: Path, path_type: str) -> None:
    """Validate path existence and permissions"""
    try:
        # Ensure path exists
        if not path.exists():
            debug_log("PATH", f"{path_type.title()} does not exist: {path}")
            return

        # Check if path is of correct type (file or directory)
        if path_type == "directory" and not path.is_dir():
            raise RuntimeError(f"Expected directory but found file: {path}")
        elif path_type == "file" and not path.is_file():
            raise RuntimeError(f"Expected file but found directory: {path}")

        # Check read permissions
        try:
            if path.is_file():
                with open(path, 'rb'):
                    pass
        except PermissionError:
            raise RuntimeError(f"No read permission for: {path}")

        # Check write permissions by trying to touch a temporary file
        if path.is_dir():
            test_file = path / ".write_test"
            try:
                test_file.touch()
                test_file.unlink()
            except PermissionError:
                raise RuntimeError(f"No write permission for directory: {path}")
        
        debug_log("PATH", f"Validated {path_type}: {path}")
        debug_log("PATH", f"├─ Absolute: {path.absolute()}")
        debug_log("PATH", f"└─ Parent: {path.parent}")
            
    except Exception as e:
        raise RuntimeError(f"Path validation failed for {path_type} {path}: {str(e)}")

def init_database_directories() -> None:
    """Initialize database directories for all environments"""
    debug_log("DB", "Initializing database directories")
    
    # Create directories for each environment mode
    for mode in EnvironmentMode:
        db_path = settings.db.get_db_path(mode)
        db_dir = db_path.parent
        db_dir.mkdir(parents=True, exist_ok=True)
        debug_log("DB", f"Created directory for {mode.value}: {db_dir}")

def validate_database_operation() -> None:
    """Validate that we're operating on the correct database."""
    current_db = Path(settings.database_url).resolve()
    test_db = settings.db.get_db_path(settings.environment.__class__.TEST).resolve()
    prod_db = settings.db.get_db_path(settings.environment.__class__.PROD).resolve()
    
    # Prevent test operations on non-test databases
    if settings.is_test_mode and current_db != test_db:
        raise RuntimeError(f"Test mode operations attempted on non-test database: {current_db}")
    
    # Prevent dev/test operations on prod database
    if not settings.is_prod_mode and current_db == prod_db:
        raise RuntimeError(f"Development operations attempted on production database")

async def init_db(force: bool = False):
    """Initialize the database with all required tables."""
    debug_log("DB", f"Initializing database: {settings.database_url}")
    debug_log("DB", f"Mode: {'TEST' if settings.is_test_mode else 'DEV'}")
    
    # Extra validation for database operations
    validate_database_operation()
    
    # In TEST_MODE, we always drop tables
    # In DEV_MODE, we only drop if force=True
    should_drop = settings.is_test_mode or force
    
    if should_drop and not settings.is_test_mode:
        debug_log("WARNING", "Forced table drop requested on DEV database!")
    
    debug_log("DB", f"Will drop tables: {should_drop}")
    
    async with aiosqlite.connect(settings.database_url) as db:
        try:
            # Set row factory on connection
            db.row_factory = aiosqlite.Row
            
            # Create a cursor and set its row factory
            async with db.execute("SELECT 1") as cursor:
                cursor.row_factory = aiosqlite.Row
            
            await db.execute("PRAGMA foreign_keys = ON")
            
            if should_drop:
                # Drop existing tables in reverse order of dependencies
                await db.execute("DROP TABLE IF EXISTS reactions")
                await db.execute("DROP TABLE IF EXISTS attachments")
                await db.execute("DROP TABLE IF EXISTS messages")
                await db.execute("DROP TABLE IF EXISTS channels_members")
                await db.execute("DROP TABLE IF EXISTS channels")
                await db.execute("DROP TABLE IF EXISTS users")
            
            debug_log("DB", "Creating tables if they don't exist")
            
            # Create users table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    totp_secret TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create channels table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT CHECK (
                        name IS NULL OR (
                            length(name) <= 25 AND
                            lower(name) = name
                        )
                    ),
                    type TEXT NOT NULL CHECK (type IN ('public', 'private', 'dm', 'notes')),
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (created_by) REFERENCES users (user_id),
                    CHECK (
                        (type IN ('public', 'private') AND name IS NOT NULL) OR
                        (type IN ('dm', 'notes') AND name IS NULL)
                    )
                )
            """)
            
            # Create channels_members table with enhanced constraints
            await db.execute("""
                CREATE TABLE IF NOT EXISTS channels_members (
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member')),
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (channel_id, user_id),
                    FOREIGN KEY (channel_id) REFERENCES channels (channel_id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)

            # Create trigger to enforce DM channel member count
            await db.execute("""
                CREATE TRIGGER IF NOT EXISTS check_dm_members
                BEFORE INSERT ON channels_members
                WHEN (SELECT type FROM channels WHERE channel_id = NEW.channel_id) = 'dm'
                BEGIN
                    SELECT CASE 
                        WHEN (
                            SELECT COUNT(*) 
                            FROM channels_members 
                            WHERE channel_id = NEW.channel_id
                        ) >= 2
                        THEN RAISE(ABORT, 'DM channels cannot have more than 2 members')
                    END;
                END;
            """)

            # Create trigger to enforce Notes channel single member
            await db.execute("""
                CREATE TRIGGER IF NOT EXISTS check_notes_members
                BEFORE INSERT ON channels_members
                WHEN (SELECT type FROM channels WHERE channel_id = NEW.channel_id) = 'notes'
                BEGIN
                    SELECT CASE 
                        WHEN (
                            SELECT COUNT(*) 
                            FROM channels_members 
                            WHERE channel_id = NEW.channel_id
                        ) >= 1
                        THEN RAISE(ABORT, 'Notes channels can only have 1 member')
                    END;
                END;
            """)

            # Create trigger to cleanup empty channels and their content
            await db.execute("""
                CREATE TRIGGER IF NOT EXISTS cleanup_empty_channels
                AFTER DELETE ON channels_members
                WHEN NOT EXISTS (
                    SELECT 1 FROM channels_members 
                    WHERE channel_id = OLD.channel_id
                )
                AND (
                    SELECT type FROM channels 
                    WHERE channel_id = OLD.channel_id
                ) IN ('public', 'private')
                BEGIN
                    -- Delete all reactions to messages in the channel
                    DELETE FROM reactions
                    WHERE message_id IN (
                        SELECT message_id FROM messages
                        WHERE channel_id = OLD.channel_id
                    );
                    
                    -- Delete all attachments for messages in the channel
                    DELETE FROM attachments
                    WHERE message_id IN (
                        SELECT message_id FROM messages
                        WHERE channel_id = OLD.channel_id
                    );
                    
                    -- Delete all messages in the channel
                    DELETE FROM messages
                    WHERE channel_id = OLD.channel_id;
                    
                    -- Finally delete the channel itself
                    DELETE FROM channels
                    WHERE channel_id = OLD.channel_id;
                END;
            """)
            
            # Create messages table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    parent_id INTEGER,
                    is_deleted BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (channel_id) REFERENCES channels (channel_id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (parent_id) REFERENCES messages (message_id)
                )
            """)
            
            # Create attachments table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS attachments (
                    attachment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER NOT NULL,
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    mime_type TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (message_id) REFERENCES messages (message_id)
                )
            """)
            
            # Create reactions table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reactions (
                    message_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    emoji TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (message_id, user_id, emoji),
                    FOREIGN KEY (message_id) REFERENCES messages (message_id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            await db.commit()
            debug_log("DB", "Database initialization complete")
            
        except Exception as e:
            debug_log("ERROR", f"Database initialization failed: {str(e)}")
            raise

async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Get database connection with proper mode validation."""
    validate_database_operation()
    debug_log("DB", f"Opening connection: {settings.database_url}")
    db = await aiosqlite.connect(settings.database_url)
    try:
        # Set row factory on connection
        db.row_factory = aiosqlite.Row
        
        # Create a cursor and set its row factory
        async with db.execute("SELECT 1") as cursor:
            cursor.row_factory = aiosqlite.Row
        
        await db.execute("PRAGMA foreign_keys = ON")
        yield db
    finally:
        await db.close()
        debug_log("DB", f"Closed connection: {settings.database_url}")

# Initialize database directories on module import
init_database_directories() 