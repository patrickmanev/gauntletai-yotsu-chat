import aiosqlite
import os
from typing import AsyncGenerator

DATABASE_URL = "yotsu_chat.db"

async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    db = await aiosqlite.connect(DATABASE_URL)
    try:
        # Enable foreign keys
        await db.execute("PRAGMA foreign_keys = ON")
        # Make sqlite return dictionaries instead of tuples
        db.row_factory = aiosqlite.Row
        yield db
    finally:
        await db.close()

async def init_db():
    """Initialize the database with all required tables"""
    async with aiosqlite.connect(DATABASE_URL) as db:
        try:
            # Enable foreign keys
            await db.execute("PRAGMA foreign_keys = ON")
            
            # Drop existing tables in reverse order of dependencies
            await db.execute("DROP TABLE IF EXISTS reactions")
            await db.execute("DROP TABLE IF EXISTS attachments")
            await db.execute("DROP TABLE IF EXISTS messages")
            await db.execute("DROP TABLE IF EXISTS channels_members")
            await db.execute("DROP TABLE IF EXISTS channels")
            await db.execute("DROP TABLE IF EXISTS users")
            
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