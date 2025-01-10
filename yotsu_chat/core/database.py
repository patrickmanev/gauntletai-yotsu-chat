import aiosqlite
import os
from typing import AsyncGenerator, Literal
from pathlib import Path
from datetime import datetime

def debug_log(category: str, message: str) -> None:
    """Print debug message with timestamp and category"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{category:^12}] {message}")

# Environment mode handling
Mode = Literal["TEST", "DEV", "PROD"]
ENV_MODE = os.getenv("ENV_MODE", "DEV").upper()
if ENV_MODE not in ("TEST", "DEV", "PROD"):
    debug_log("WARNING", f"Invalid ENV_MODE: {ENV_MODE}, defaulting to DEV")
    ENV_MODE = "DEV"

# For backward compatibility
TEST_MODE = ENV_MODE == "TEST"

debug_log("CONFIG", f"Environment mode: {ENV_MODE}")

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

# Get the project root directory (parent of the package directory)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
debug_log("INIT", f"Project root: {PROJECT_ROOT}")

# Database paths using platform-agnostic path joining
DB_ROOT = PROJECT_ROOT / "data" / "db"
TEST_DB_PATH = DB_ROOT / "test" / "test_yotsu_chat.db"
DEV_DB_PATH = DB_ROOT / "dev" / "dev_yotsu_chat.db"
PROD_DB_PATH = DB_ROOT / "prod" / "prod_yotsu_chat.db"

# Resolve the paths after construction
TEST_DB_PATH = TEST_DB_PATH.resolve()
DEV_DB_PATH = DEV_DB_PATH.resolve()
PROD_DB_PATH = PROD_DB_PATH.resolve()

debug_log("INIT", f"Database paths:")
debug_log("INIT", f"├─ Root: {DB_ROOT}")
debug_log("INIT", f"├─ Test DB: {TEST_DB_PATH}")
debug_log("INIT", f"├─ Dev DB: {DEV_DB_PATH}")
debug_log("INIT", f"└─ Prod DB: {PROD_DB_PATH}")

# Set the database path based on environment mode
DATABASE_PATHS = {
    "TEST": TEST_DB_PATH,
    "DEV": DEV_DB_PATH,
    "PROD": PROD_DB_PATH
}

DATABASE_URL = str(DATABASE_PATHS[ENV_MODE])
debug_log("INIT", f"Using {ENV_MODE} database: {DATABASE_URL}")

# Ensure database directories exist (using parents=True for nested creation)
DB_ROOT.mkdir(parents=True, exist_ok=True)
TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DEV_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
PROD_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Validate paths after creation
validate_path(DB_ROOT, "directory")
validate_path(TEST_DB_PATH.parent, "directory")
validate_path(DEV_DB_PATH.parent, "directory")
validate_path(PROD_DB_PATH.parent, "directory")

# If database files exist, validate them
for db_path in (TEST_DB_PATH, DEV_DB_PATH, PROD_DB_PATH):
    if db_path.exists():
        validate_path(db_path, "file")

def validate_database_operation():
    """Validate that we're operating on the correct database"""
    current_db = Path(DATABASE_URL).resolve()
    
    # Prevent test operations on non-test databases
    if TEST_MODE and current_db != TEST_DB_PATH:
        raise RuntimeError(f"TEST_MODE operations attempted on non-test database: {current_db}")
    
    # Prevent dev/test operations on prod database
    if ENV_MODE != "PROD" and current_db == PROD_DB_PATH:
        raise RuntimeError(f"Development operations attempted on production database")

async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Get database connection with proper mode validation"""
    validate_database_operation()
    debug_log("DB", f"Opening connection: {DATABASE_URL}")
    db = await aiosqlite.connect(DATABASE_URL)
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
        debug_log("DB", f"Closed connection: {DATABASE_URL}")

async def init_db(force: bool = False):
    """Initialize the database with all required tables."""
    debug_log("DB", f"Initializing database: {DATABASE_URL}")
    debug_log("DB", f"Mode: {'TEST' if TEST_MODE else 'DEV'}")
    
    # Extra validation for database operations
    validate_database_operation()
    
    # In TEST_MODE, we always drop tables
    # In DEV_MODE, we only drop if force=True
    should_drop = TEST_MODE or force
    
    if should_drop and not TEST_MODE:
        debug_log("WARNING", "Forced table drop requested on DEV database!")
    
    debug_log("DB", f"Will drop tables: {should_drop}")
    
    async with aiosqlite.connect(DATABASE_URL) as db:
        try:
            # Set row factory on connection
            db.row_factory = aiosqlite.Row
            
            # Create a cursor and set its row factory
            async with db.execute("SELECT 1") as cursor:
                cursor.row_factory = aiosqlite.Row
            
            await db.execute("PRAGMA foreign_keys = ON")
            
            if should_drop:
                debug_log("DB", "Dropping all tables")
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