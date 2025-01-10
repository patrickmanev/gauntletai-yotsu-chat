from typing import Dict, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio
from contextlib import suppress
from datetime import datetime, timedelta
from .auth import decode_token
from ..utils.errors import YotsuError, ErrorCode
import logging
import os
from yotsu_chat.core.database import debug_log

logger = logging.getLogger(__name__)

class WebSocketError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)

class ConnectionManager:
    """WebSocket connection manager"""
    def __init__(self):
        self._lock = asyncio.Lock()
        self.active_connections: Dict[str, WebSocket] = {}  # Dict of connection_id -> WebSocket
        self.channel_connections: Dict[int, Set[str]] = {}  # Dict of channel_id -> set of connection_ids
        self.connection_health: Dict[str, datetime] = {}  # Dict of connection_id -> last pong time
        self.connection_users: Dict[str, int] = {}  # Dict of connection_id -> user_id
        self._health_check_task = None  # Task for periodic health checks
        logger.info("ConnectionManager initialized")
    
    async def authenticate_connection(self, websocket: WebSocket) -> int:
        """Authenticate WebSocket connection using token"""
        try:
            token = websocket.query_params.get("token")
            if not token:
                logger.error("WebSocket authentication failed: Missing token")
                raise WebSocketError(1008, "Missing authentication token")
            
            # In test mode, extract user_id from query params
            if os.getenv("TEST_MODE") == "true":
                user_id = int(websocket.query_params.get("user_id", "1"))
                return user_id
            
            try:
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
        self.connection_health[connection_id] = datetime.now()
        self.connection_users[connection_id] = user_id
        debug_log("WS", f"Active connections after connect: {len(self.active_connections)}")
        
        # Start health check task if not running
        if not self._health_check_task or self._health_check_task.done():
            logger.info("Starting health check task")
            self._health_check_task = asyncio.create_task(self._check_connection_health())
        
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
            logger.info(f"Connection {connection_id} joining channel {channel_id}")
            if channel_id not in self.channel_connections:
                debug_log("WS", f"Creating new channel set for channel {channel_id}")
                self.channel_connections[channel_id] = set()
            self.channel_connections[channel_id].add(connection_id)
            logger.info(f"Added connection {connection_id} to channel {channel_id}, total connections: {len(self.channel_connections[channel_id])}")
    
    async def leave_channel(self, connection_id: str, channel_id: int):
        """Remove a WebSocket connection from a channel"""
        async with self._lock:
            if channel_id in self.channel_connections:
                self.channel_connections[channel_id].discard(connection_id)
                if not self.channel_connections[channel_id]:
                    del self.channel_connections[channel_id]
                logger.info(f"Removed connection {connection_id} from channel {channel_id}")
    
    async def broadcast_to_channel(self, channel_id: int, message: dict):
        """Broadcast message to all connections in a channel"""
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
        self.connection_health[connection_id] = datetime.now()
        debug_log("WS", f"Received pong from connection {connection_id}")
    
    async def send_error(self, connection_id: str, code: int, message: str):
        """Send error message to WebSocket"""
        try:
            websocket = self.active_connections.get(connection_id)
            if websocket:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "data": {
                        "code": code,
                        "message": message
                    }
                }))
        except Exception as e:
            logger.error(f"Error sending error message to {connection_id}: {str(e)}")
    
    async def _check_connection_health(self):
        """Periodic health check for all connections"""
        while True:
            try:
                # Check every 30 seconds in production, 1 second during tests
                await asyncio.sleep(30 if not __debug__ else 1)
                now = datetime.now()
                dead_connections = set()
                
                async with self._lock:
                    for conn_id, last_pong in self.connection_health.items():
                        try:
                            if now - last_pong > timedelta(seconds=90):  # No pong for 90 seconds
                                dead_connections.add(conn_id)
                            else:
                                websocket = self.active_connections.get(conn_id)
                                if websocket:
                                    await websocket.send_text(json.dumps({"type": "ping"}))
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

# Global connection manager instance
manager = ConnectionManager() 