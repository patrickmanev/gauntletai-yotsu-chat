from typing import Dict, Set, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio
from contextlib import suppress
from datetime import datetime, timedelta, UTC
from .auth import decode_token
from ..utils.errors import YotsuError, ErrorCode
from ..utils import debug_log
import logging
from .config import get_settings
from websockets.exceptions import InvalidHandshake
import aiosqlite

logger = logging.getLogger(__name__)
settings = get_settings()

class WebSocketError(InvalidHandshake):
    """Custom WebSocket error that includes close codes for better client handling"""
    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(message)

class ConnectionManager:
    """WebSocket connection manager"""
    def __init__(self):
        self._lock = asyncio.Lock()
        self.active_connections: Dict[str, WebSocket] = {}  # Dict of connection_id -> WebSocket
        self.channel_connections: Dict[int, Set[str]] = {}  # Dict of channel_id -> set of connection_ids
        self.connection_health: Dict[str, Dict[str, Any]] = {}  # Dict of connection_id -> health info
        self.connection_users: Dict[str, int] = {}  # Dict of connection_id -> user_id
        self.connection_rate_limits: Dict[str, Dict[str, Any]] = {}  # Dict of connection_id -> rate limit info
        self.user_rate_limits: Dict[int, Dict[str, Any]] = {}  # Dict of user_id -> rate limit info
        self._health_check_task = None  # Task for periodic health checks
        logger.info("ConnectionManager initialized")
    
    async def authenticate_connection(self, websocket: WebSocket) -> int:
        """Authenticate WebSocket connection using token"""
        try:
            token = websocket.query_params.get("token")
            if not token:
                logger.error("WebSocket authentication failed: Missing token")
                raise WebSocketError(1008, "Missing authentication token")
            
            try:
                from .auth import decode_token
                payload = decode_token(token)
                if not payload:
                    logger.error("WebSocket authentication failed: Invalid token")
                    raise WebSocketError(1008, "Invalid authentication token")
                
                return payload["user_id"]
            except Exception as e:
                logger.error(f"WebSocket authentication failed: {str(e)}")
                raise WebSocketError(1008, "Invalid authentication token")
        except WebSocketError:
            raise
        except Exception as e:
            logger.error(f"WebSocket authentication failed: {str(e)}")
            raise WebSocketError(1008, "Authentication failed")
    
    async def connect(self, websocket: WebSocket, user_id: int, connection_id: str):
        """Connect a WebSocket and add it to active connections"""
        logger.info(f"Accepting WebSocket connection {connection_id} for user {user_id}")
        await websocket.accept()
        
        self.active_connections[connection_id] = websocket
        self.connection_health[connection_id] = {
            "last_pong": datetime.now(UTC),
            "pending_ping": False
        }
        self.connection_users[connection_id] = user_id
        
        # Initialize rate limiting for user if not exists
        if user_id not in self.user_rate_limits:
            self.user_rate_limits[user_id] = {
                "message_count": 0,
                "last_reset": datetime.now(UTC),
                "rate_limit": 10,  # messages per minute
                "time_window": 60  # seconds
            }
        
        debug_log("WS", f"Active connections after connect: {len(self.active_connections)}")
        
        # Start health check task if not running
        if not self._health_check_task or self._health_check_task.done():
            logger.info("Starting health check task")
            self._health_check_task = asyncio.create_task(self._check_connection_health())
        
        # Subscribe to existing channels
        await self._subscribe_to_existing_channels(connection_id, user_id)
        
        logger.info(f"WebSocket {connection_id} connected for user {user_id}")
    
    async def disconnect(self, connection_id: str):
        """Disconnect a WebSocket and remove it from active connections"""
        try:
            websocket = self.active_connections.pop(connection_id, None)
            user_id = self.connection_users.pop(connection_id, None)
            self.connection_health.pop(connection_id, None)
            
            # Remove from all channels
            for channel_connections in self.channel_connections.values():
                channel_connections.discard(connection_id)
            
            # Clean up empty channel sets
            self.channel_connections = {
                k: v for k, v in self.channel_connections.items() if v
            }
            
            # Clean up rate limit info if this was user's last connection
            if user_id and not any(uid == user_id for uid in self.connection_users.values()):
                self.user_rate_limits.pop(user_id, None)
            
            if websocket:
                try:
                    await websocket.close()
                except Exception:
                    pass
            
            if user_id:
                logger.info(f"WebSocket {connection_id} disconnected for user {user_id}")
            else:
                logger.info(f"WebSocket {connection_id} disconnected for unknown user")
        except Exception as e:
            logger.error(f"Error during WebSocket disconnect: {str(e)}")
    
    async def join_channel(self, connection_id: str, channel_id: int):
        """Add a WebSocket connection to a channel"""
        async with self._lock:
            debug_log("WS", f"Joining channel {channel_id} with connection {connection_id}")
            debug_log("WS", f"├─ Connection exists: {connection_id in self.active_connections}")
            debug_log("WS", f"├─ Channel exists: {channel_id in self.channel_connections}")
            debug_log("WS", f"├─ Current channel_connections: {self.channel_connections}")
            debug_log("WS", f"├─ Current active_connections: {list(self.active_connections.keys())}")
            debug_log("WS", f"├─ Current connection_users: {self.connection_users}")
            
            if channel_id not in self.channel_connections:
                debug_log("WS", f"├─ Creating new channel set for channel {channel_id}")
                self.channel_connections[channel_id] = set()
                debug_log("WS", f"├─ Channel set created: {self.channel_connections[channel_id]}")
            
            self.channel_connections[channel_id].add(connection_id)
            debug_log("WS", f"└─ Added connection {connection_id} to channel {channel_id}, total connections: {len(self.channel_connections[channel_id])}")
            debug_log("WS", f"  └─ Final channel_connections state: {self.channel_connections}")
            logger.info(f"Added connection {connection_id} to channel {channel_id}, total connections: {len(self.channel_connections[channel_id])}")
    
    async def leave_channel(self, connection_id: str, channel_id: int):
        """Remove a WebSocket connection from a channel"""
        async with self._lock:
            if channel_id in self.channel_connections:
                self.channel_connections[channel_id].discard(connection_id)
                if not self.channel_connections[channel_id]:
                    del self.channel_connections[channel_id]
                logger.info(f"Removed connection {connection_id} from channel {channel_id}")
    
    async def broadcast_to_channel(self, channel_id: int, message: dict) -> None:
        """Broadcast a message to all connections in a channel."""
        # Initialize channel if needed
        await self.initialize_channel(channel_id)
        
        # Get active connections for channel
        connections = self.channel_connections.get(channel_id, set())
        if not connections:
            debug_log("WS", f"No clients connected to channel {channel_id} for broadcast")
            return
        
        async with self._lock:
            logger.info(f"Broadcasting to channel {channel_id}")
            
            if channel_id not in self.channel_connections:
                logger.warning(f"Attempted to broadcast to non-existent channel {channel_id}")
                return
            
            connection_ids = self.channel_connections[channel_id].copy()
            if not connection_ids:
                logger.warning(f"No active connections in channel {channel_id}")
                return
            
            message_text = json.dumps(message)
            dead_connections = set()
            success_count = 0
            
            logger.info(f"Broadcasting to channel {channel_id}: {message}")
            logger.info(f"Active connections in channel: {len(connection_ids)}")
            
            for conn_id in connection_ids:
                try:
                    websocket = self.active_connections.get(conn_id)
                    if not websocket:
                        logger.warning(f"Connection {conn_id} not found")
                        dead_connections.add(conn_id)
                        continue
                        
                    await websocket.send_text(message_text)
                    success_count += 1
                    debug_log("WS", f"Successfully sent message to connection {conn_id}")
                except Exception as e:
                    logger.error(f"Error broadcasting to connection {conn_id}: {str(e)}")
                    dead_connections.add(conn_id)
            
            if dead_connections:
                for conn_id in dead_connections:
                    await self.disconnect(conn_id)
                    
            logger.info(f"Channel broadcast complete: {success_count}/{len(connection_ids)} successful")
    
    async def broadcast_to_all(self, message: dict) -> None:
        """Broadcast a message to all active connections."""
        logger.info(f"Broadcasting to all connections: {message}")
        logger.info(f"Total active connections: {len(self.active_connections)}")
        try:
            message_text = json.dumps(message)
            dead_connections = set()
            success_count = 0
            
            for connection_id, websocket in self.active_connections.items():
                try:
                    debug_log("WS", f"Sending to connection {connection_id}")
                    await websocket.send_text(message_text)
                    success_count += 1
                    debug_log("WS", f"Successfully sent to connection {connection_id}")
                except Exception as e:
                    logger.error(f"Error sending to connection {connection_id}: {str(e)}")
                    dead_connections.add(connection_id)
            
            # Clean up dead connections
            for conn_id in dead_connections:
                await self.disconnect(conn_id)
            
            logger.info(f"Broadcast complete: {success_count}/{len(self.active_connections)} successful")
            
        except Exception as e:
            logger.error(f"Error in broadcast_to_all: {str(e)}")
            logger.exception("Full traceback:")
    
    async def handle_pong(self, connection_id: str):
        """Update last pong time for a connection"""
        if connection_id in self.connection_health:
            self.connection_health[connection_id]["last_pong"] = datetime.now(UTC)
            self.connection_health[connection_id]["pending_ping"] = False
        debug_log("WS", f"Received pong from connection {connection_id}")
    
    async def send_error(self, connection_id: str, code: int, message: str):
        """Send error message to WebSocket"""
        try:
            websocket = self.active_connections.get(connection_id)
            if websocket:
                error_message = {
                    "type": "system.error",
                    "data": {
                        "code": code,
                        "message": message
                    }
                }
                await websocket.send_text(json.dumps(error_message))
                logger.error(f"Sent error to {connection_id}: {message}")
        except Exception as e:
            logger.error(f"Error sending error message to {connection_id}: {str(e)}")
    
    async def _check_connection_health(self):
        """Periodic health check for all connections"""
        while True:
            try:
                # Check every 30 seconds in production, 1 second during tests
                await asyncio.sleep(30 if not __debug__ else 1)
                now = datetime.now(UTC)
                dead_connections = set()
                
                async with self._lock:
                    for conn_id, health in self.connection_health.items():
                        try:
                            if now - health["last_pong"] > timedelta(seconds=90):  # No pong for 90 seconds
                                dead_connections.add(conn_id)
                            else:
                                websocket = self.active_connections.get(conn_id)
                                if websocket:
                                    await websocket.send_text(json.dumps({"type": "ping"}))
                                    self.connection_health[conn_id]["pending_ping"] = True
                        except Exception:
                            dead_connections.add(conn_id)
                
                # Clean up dead connections
                for conn_id in dead_connections:
                    try:
                        await self.disconnect(conn_id)
                    except Exception:
                        pass
                    logger.warning(f"Removed dead connection {conn_id} during health check")
            except Exception as e:
                logger.error(f"Error in health check: {str(e)}")
            except asyncio.CancelledError:
                break
    
    async def cleanup(self):
        """Cleanup all WebSocket connections and tasks"""
        # Cancel health check task
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Close all connections
        for connection_id in list(self.active_connections.keys()):
            await self.disconnect(connection_id)
        
        # Clear all state
        self.active_connections.clear()
        self.channel_connections.clear()
        self.connection_health.clear()
        self.connection_users.clear()
        self.connection_rate_limits.clear()
        self.user_rate_limits.clear()
        self._health_check_task = None
    
    async def send_to_connection(self, connection_id: str, message: dict) -> None:
        """Send a message to a specific connection."""
        websocket = self.active_connections.get(connection_id)
        if websocket:
            try:
                await websocket.send_json(message)
                debug_log("WS", f"Successfully sent message to connection {connection_id}")
            except Exception as e:
                logger.error(f"Error sending to connection {connection_id}: {e}")
                # Connection may be dead, remove it
                await self.disconnect(connection_id)
        else:
            logger.warning(f"Attempted to send to non-existent connection {connection_id}")
    
    async def initialize_channel(self, channel_id: int) -> None:
        """Initialize a WebSocket channel if it doesn't exist."""
        if channel_id not in self.channel_connections:
            self.channel_connections[channel_id] = set()
            debug_log("WS", f"Initialized WebSocket channel {channel_id}")
    
    async def check_rate_limit(self, connection_id: str) -> bool:
        """Check if a connection has exceeded its rate limit"""
        user_id = self.connection_users.get(connection_id)
        if not user_id:
            return False
            
        rate_limit = self.user_rate_limits.get(user_id)
        if not rate_limit:
            return False
            
        now = datetime.now(UTC)
        time_since_reset = (now - rate_limit["last_reset"]).total_seconds()
        
        # Reset counter if time window has passed
        if time_since_reset >= rate_limit["time_window"]:
            rate_limit["message_count"] = 0
            rate_limit["last_reset"] = now
            return False
            
        # Check if limit exceeded
        return rate_limit["message_count"] >= rate_limit["rate_limit"]
    
    async def increment_message_count(self, connection_id: str):
        """Increment message count for a user"""
        user_id = self.connection_users.get(connection_id)
        if not user_id or user_id not in self.user_rate_limits:
            return
            
        self.user_rate_limits[user_id]["message_count"] += 1
    
    async def handle_client_message(self, connection_id: str, message: str):
        """Handle incoming client message with rate limiting"""
        try:
            # Check rate limit before processing
            if await self.check_rate_limit(connection_id):
                # Get user_id and all their connections
                user_id = self.connection_users.get(connection_id)
                if user_id:
                    user_connections = [
                        conn_id for conn_id, uid in self.connection_users.items()
                        if uid == user_id
                    ]
                    # Send error to all user's connections
                    for conn_id in user_connections:
                        await self.send_error(conn_id, 429, "Rate limit exceeded")
                return
                
            # Increment message count
            await self.increment_message_count(connection_id)
            
            # Process message...
            # Add your message handling logic here
            
        except Exception as e:
            logger.error(f"Error handling client message: {str(e)}")
            await self.send_error(connection_id, 500, "Internal server error")
    
    async def send_ping(self, connection_id: str):
        """Send a ping message to a connection"""
        websocket = self.active_connections.get(connection_id)
        if websocket:
            await websocket.send_text(json.dumps({"type": "ping"}))
            self.connection_health[connection_id]["pending_ping"] = True
            debug_log("WS", f"Sent ping to connection {connection_id}")
    
    async def _subscribe_to_existing_channels(self, connection_id: str, user_id: int):
        """Subscribe a connection to all channels the user is a member of:
        1. All public/private channels they're a member of (any role)
        2. All their DM channels
        3. Their notes channel
        """
        try:
            # Import here to avoid circular imports
            from ..services.channel_service import channel_service
            
            debug_log("WS", f"Subscribing connection {connection_id} to existing channels")
            async with aiosqlite.connect(settings.database_url) as db:
                # Get all channels the user is a member of
                debug_log("WS", f"├─ Getting channels for user {user_id}")
                channels = await channel_service.list_channels(db, user_id)
                debug_log("WS", f"├─ Found {len(channels)} total channels")
                
                # Group channels by type for logging
                channel_types = {}
                for channel in channels:
                    channel_type = channel["type"]
                    if channel_type not in channel_types:
                        channel_types[channel_type] = []
                    channel_types[channel_type].append(channel["channel_id"])
                
                debug_log("WS", f"├─ Channel breakdown by type:")
                for type_name, channel_ids in channel_types.items():
                    debug_log("WS", f"├─── {type_name}: {len(channel_ids)} channels - {channel_ids}")
                
                # Subscribe to all channels
                for channel in channels:
                    channel_id = channel["channel_id"]
                    channel_type = channel["type"]
                    debug_log("WS", f"├─ Subscribing to {channel_type} channel {channel_id}")
                    await self.join_channel(connection_id, channel_id)
                    debug_log("WS", f"└─── Subscribed to channel {channel_id}")
                
                debug_log("WS", f"Channel subscription complete for user {user_id}")
                debug_log("WS", f"Final channel_connections state: {self.channel_connections}")
        except Exception as e:
            logger.error(f"Failed to subscribe to existing channels: {str(e)}")
            # Don't raise - this is not critical enough to fail the connection

# Global connection manager instance
manager = ConnectionManager() 