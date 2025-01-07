"""Disabled presence tracking module"""

# from datetime import datetime
# from enum import Enum
from typing import Dict, Set
import logging
# import json

# from app.core.ws_core import manager

logger = logging.getLogger(__name__)

class PresenceState:
    """Disabled presence states"""
    ONLINE = "ONLINE"
    AWAY = "AWAY"
    OFFLINE = "OFFLINE"

class PresenceManager:
    """Disabled presence manager"""
    def __init__(self):
        logger.info("PresenceManager disabled")
    
    async def handle_connect(self, user_id: int, connection_id: str):
        """Disabled connect handler"""
        pass
    
    async def handle_disconnect(self, user_id: int, connection_id: str):
        """Disabled disconnect handler"""
        pass
    
    async def update_focus(self, user_id: int, connection_id: str, in_focus: bool):
        """Disabled focus update handler"""
        pass
    
    def _get_user_state(self, user_id: int) -> str:
        """Disabled state getter"""
        return PresenceState.OFFLINE

# Global presence manager instance (disabled)
presence_manager = PresenceManager() 