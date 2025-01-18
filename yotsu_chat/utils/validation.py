"""Validation utilities for Yotsu Chat."""
import aiosqlite
from typing import List, Union, Set

async def verify_users_exist(db: aiosqlite.Connection, user_ids: Union[int, List[int]]) -> Set[int]:
    """Verify that users exist in the database.
    
    Args:
        db: Database connection
        user_ids: Single user ID or list of user IDs to verify
        
    Returns:
        Set of user IDs that don't exist in the database
    """
    # Convert single value to list
    user_ids_list = [user_ids] if isinstance(user_ids, int) else user_ids
    
    placeholders = ','.join('?' * len(user_ids_list))
    async with db.execute(
        f"""SELECT user_id FROM users 
        WHERE user_id IN ({placeholders})""",
        user_ids_list
    ) as cursor:
        existing_users = {row[0] for row in await cursor.fetchall()}
        return set(user_ids_list) - existing_users 