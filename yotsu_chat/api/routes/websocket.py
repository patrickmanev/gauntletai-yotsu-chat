from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException
from yotsu_chat.core.ws_core import manager
from yotsu_chat.core.presence import presence_manager
from yotsu_chat.utils import debug_log
from yotsu_chat.core.config import get_settings
import logging
import json
import uuid

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    try:
        # Authenticate connection
        user_id = await manager.authenticate_connection(websocket)
        connection_id = str(uuid.uuid4())
        
        # Accept connection
        await manager.connect(websocket, user_id, connection_id)
        await presence_manager.handle_connect(user_id, connection_id)
        
        # Send connection_id to client
        await websocket.send_json({
            "type": "connection_id",
            "data": {
                "connection_id": connection_id
            }
        })
        
        try:
            while True:
                # Wait for messages
                message_text = await websocket.receive_text()
                debug_log("WS", f"Received message from connection {connection_id}: {message_text}")
                
                try:
                    message = json.loads(message_text)
                    message_type = message.get("type")
                    
                    if message_type == "ping":
                        await websocket.send_text(json.dumps({"type": "pong"}))
                    
                    elif message_type == "pong":
                        await manager.handle_pong(connection_id)
                    
                    elif message_type == "join_channel":
                        channel_id = message.get("data", {}).get("channel_id")
                        if channel_id is not None:
                            await manager.join_channel(connection_id, channel_id)
                    
                    elif message_type == "leave_channel":
                        channel_id = message.get("data", {}).get("channel_id")
                        if channel_id is not None:
                            await manager.leave_channel(connection_id, channel_id)
                    
                    elif message_type == "window_focus":
                        in_focus = message.get("data", {}).get("in_focus", False)
                        await presence_manager.update_focus(user_id, connection_id, in_focus)
                    
                    else:
                        logger.warning(f"Unknown message type from connection {connection_id}: {message_type}")
                        await manager.send_error(connection_id, 400, f"Unknown message type: {message_type}")
                
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from connection {connection_id}: {message_text}")
                    await manager.send_error(connection_id, 400, "Invalid JSON message")
                except Exception as e:
                    logger.error(f"Error handling message from connection {connection_id}: {str(e)}")
                    await manager.send_error(connection_id, 500, "Internal server error")
        
        except WebSocketDisconnect:
            logger.info(f"WebSocket {connection_id} disconnected normally")
        finally:
            # Clean up connection
            await manager.disconnect(connection_id)
            await presence_manager.handle_disconnect(user_id, connection_id)
    
    except Exception as e:
        logger.error(f"Error in websocket_endpoint: {str(e)}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass 