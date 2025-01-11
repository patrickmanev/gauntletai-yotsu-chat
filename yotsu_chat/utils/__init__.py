"""Utility functions and helpers"""

from datetime import datetime

def debug_log(category: str, message: str, exc_info: bool = False) -> None:
    """Log a debug message with a category prefix and timestamp.
    
    Args:
        category: Category of the log message (e.g. AUTH, DB, etc.)
        message: The message to log
        exc_info: Whether to include exception info in the log
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [{category}] {message}")
    if exc_info:
        import traceback
        print(traceback.format_exc())
