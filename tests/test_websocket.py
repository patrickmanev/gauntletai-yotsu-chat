import pytest
import asyncio
from typing import Dict, Any, List
from httpx import AsyncClient
from app.core.ws_core import manager as ws_manager
import json
import uuid

pytestmark = pytest.mark.asyncio

class MockWebSocket:
    def __init__(self):
        self.sent_messages: List[str] = []
        self.closed = False
        self.close_code = None
        self.close_reason = None
        self.query_params = {}
        self.accepted = False
        
    async def send_text(self, message: str):
        print(f"MockWebSocket received message: {message}")  # Debug logging
        self.sent_messages.append(message)
    
    async def close(self, code: int = 1000, reason: str = ""):
        print(f"MockWebSocket closed with code {code}: {reason}")  # Debug logging
        self.closed = True
        self.close_code = code
        self.close_reason = reason
        
    async def accept(self):
        print("MockWebSocket accepted connection")  # Debug logging
        self.accepted = True
        
    async def receive_text(self):
        # Mock receiving a pong message
        return json.dumps({"type": "pong"})

@pytest.fixture(autouse=True)
async def cleanup_manager():
    """Cleanup the WebSocket manager after each test"""
    yield
    await ws_manager.cleanup()
    ws_manager._health_check_task = None
    ws_manager.active_connections.clear()
    ws_manager.channel_connections.clear()
    ws_manager.connection_health.clear()

async def test_websocket_authentication(access_token: str):
    """Test WebSocket authentication"""
    # Temporarily disable test mode for this test
    import os
    old_test_mode = os.getenv("TEST_MODE")
    os.environ["TEST_MODE"] = "false"
    
    try:
        # Test missing token
        ws = MockWebSocket()
        with pytest.raises(Exception) as exc:
            await ws_manager.authenticate_connection(ws)
        assert "Missing authentication token" in str(exc.value)
        
        # Test invalid token
        ws = MockWebSocket()
        ws.query_params["token"] = "invalid_token"
        with pytest.raises(Exception) as exc:
            await ws_manager.authenticate_connection(ws)
        assert "Invalid authentication token" in str(exc.value)
        
        # Test valid token
        ws = MockWebSocket()
        ws.query_params["token"] = access_token
        user_id = await ws_manager.authenticate_connection(ws)
        assert user_id == 1  # First user created in tests
    finally:
        if old_test_mode is not None:
            os.environ["TEST_MODE"] = old_test_mode
        else:
            del os.environ["TEST_MODE"]

async def test_websocket_health_check():
    """Test WebSocket health check mechanism"""
    ws = MockWebSocket()
    ws.query_params["token"] = "mock_token"  # Mock token for testing
    connection_id = str(uuid.uuid4())
    
    try:
        # Connect WebSocket
        await ws_manager.connect(ws, 1, connection_id)
        
        # Verify initial health status
        assert connection_id in ws_manager.connection_health
        
        # Simulate ping/pong
        await ws_manager.handle_pong(connection_id)
        
        # Verify health check task is running
        assert ws_manager._health_check_task is not None
        
        # Wait for ping message (up to 2 seconds)
        for _ in range(20):  # 20 * 0.1 = 2 seconds
            if any(
                json.loads(msg)["type"] == "ping"
                for msg in ws.sent_messages
            ):
                break
            await asyncio.sleep(0.1)
        
        # Verify ping message was sent
        assert any(
            json.loads(msg)["type"] == "ping"
            for msg in ws.sent_messages
        )
    finally:
        await ws_manager.disconnect(connection_id)

async def test_websocket_channel_management(access_token: str, test_channel: Dict[str, Any]):
    """Test WebSocket channel join/leave operations"""
    channel_id = test_channel["channel_id"]
    ws = MockWebSocket()
    ws.query_params["token"] = access_token
    connection_id = str(uuid.uuid4())
    
    try:
        # Connect and authenticate
        user_id = await ws_manager.authenticate_connection(ws)
        await ws_manager.connect(ws, user_id, connection_id)
        
        # Join channel
        await ws_manager.join_channel(connection_id, channel_id)
        assert connection_id in ws_manager.channel_connections[channel_id]
        
        # Leave channel
        await ws_manager.leave_channel(connection_id, channel_id)
        assert channel_id not in ws_manager.channel_connections or connection_id not in ws_manager.channel_connections[channel_id]
    finally:
        await ws_manager.disconnect(connection_id)

async def test_message_websocket_events(
    client: AsyncClient,
    access_token: str,
    test_channel: Dict[str, Any]
):
    """Test that WebSocket events are sent for message operations"""
    channel_id = test_channel["channel_id"]
    
    # Create mock WebSocket
    mock_websocket = MockWebSocket()
    mock_websocket.query_params["token"] = access_token
    connection_id = str(uuid.uuid4())
    
    try:
        # Connect and authenticate
        user_id = await ws_manager.authenticate_connection(mock_websocket)
        await ws_manager.connect(mock_websocket, user_id, connection_id)
        await ws_manager.join_channel(connection_id, channel_id)
        
        # Create a message
        response = await client.post(
            f"/api/messages/channels/{channel_id}",
            json={"content": "Test message"},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
        message_data = response.json()
        
        # Verify message.created event was sent
        assert any(
            json.loads(msg)["type"] == "message.created" and 
            json.loads(msg)["data"]["message_id"] == message_data["message_id"]
            for msg in mock_websocket.sent_messages
        )
        
        # Update message
        response = await client.put(
            f"/api/messages/{message_data['message_id']}",
            json={"content": "Updated message"},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 200
        
        # Verify message.updated event was sent
        assert any(
            json.loads(msg)["type"] == "message.updated" and 
            json.loads(msg)["data"]["message_id"] == message_data["message_id"]
            for msg in mock_websocket.sent_messages
        )
        
        # Delete message
        response = await client.delete(
            f"/api/messages/{message_data['message_id']}",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 200
        
        # Verify message.deleted event was sent
        assert any(
            json.loads(msg)["type"] == "message.deleted" and 
            json.loads(msg)["data"]["message_id"] == message_data["message_id"]
            for msg in mock_websocket.sent_messages
        )
    finally:
        await ws_manager.disconnect(connection_id)

async def test_reaction_websocket_events(
    client: AsyncClient,
    access_token: str,
    test_message: Dict[str, Any]
):
    """Test that WebSocket events are sent for reaction operations"""
    message_id = test_message["message_id"]
    channel_id = test_message["channel_id"]
    
    # Create mock WebSocket
    mock_websocket = MockWebSocket()
    mock_websocket.query_params["token"] = access_token
    connection_id = str(uuid.uuid4())
    
    try:
        # Connect and authenticate
        user_id = await ws_manager.authenticate_connection(mock_websocket)
        await ws_manager.connect(mock_websocket, user_id, connection_id)
        await ws_manager.join_channel(connection_id, channel_id)
        
        # Add reaction
        response = await client.post(
            f"/api/reactions/messages/{message_id}",
            json={"emoji": "👍"},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
        
        # Verify reaction.added event was sent
        assert any(
            json.loads(msg)["type"] == "reaction.added" and 
            json.loads(msg)["data"]["message_id"] == message_id and
            json.loads(msg)["data"]["emoji"] == "👍"
            for msg in mock_websocket.sent_messages
        )
        
        # Remove reaction
        response = await client.delete(
            f"/api/reactions/messages/{message_id}/👍",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 200
        
        # Verify reaction.removed event was sent
        assert any(
            json.loads(msg)["type"] == "reaction.removed" and 
            json.loads(msg)["data"]["message_id"] == message_id and
            json.loads(msg)["data"]["emoji"] == "👍"
            for msg in mock_websocket.sent_messages
        )
    finally:
        await ws_manager.disconnect(connection_id)

async def test_thread_message_websocket_events(
    client: AsyncClient,
    access_token: str,
    test_channel: Dict[str, Any]
):
    """Test WebSocket events for thread messages"""
    channel_id = test_channel["channel_id"]
    
    # Create mock WebSocket
    mock_websocket = MockWebSocket()
    mock_websocket.query_params["token"] = access_token
    connection_id = str(uuid.uuid4())
    
    try:
        # Connect and authenticate
        user_id = await ws_manager.authenticate_connection(mock_websocket)
        await ws_manager.connect(mock_websocket, user_id, connection_id)
        await ws_manager.join_channel(connection_id, channel_id)
        
        # Create parent message
        response = await client.post(
            f"/api/messages/channels/{channel_id}",
            json={"content": "Parent message"},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
        parent_data = response.json()
        
        # Verify parent message.created event
        assert any(
            json.loads(msg)["type"] == "message.created" and 
            json.loads(msg)["data"]["message_id"] == parent_data["message_id"]
            for msg in mock_websocket.sent_messages
        )
        
        # Create thread message
        response = await client.post(
            f"/api/messages/channels/{channel_id}",
            json={"content": "Thread message", "parent_id": parent_data["message_id"]},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
        thread_data = response.json()
        
        # Verify thread message.created event
        assert any(
            json.loads(msg)["type"] == "message.created" and 
            json.loads(msg)["data"]["message_id"] == thread_data["message_id"] and
            json.loads(msg)["data"]["parent_id"] == parent_data["message_id"]
            for msg in mock_websocket.sent_messages
        )
    finally:
        await ws_manager.disconnect(connection_id)

async def test_websocket_error_handling():
    """Test WebSocket error handling"""
    ws = MockWebSocket()
    connection_id = str(uuid.uuid4())
    
    # Add the websocket to active connections first
    ws_manager.active_connections[connection_id] = ws
    
    # Test error message sending
    await ws_manager.send_error(connection_id, 4000, "Test error")
    error_message = json.loads(ws.sent_messages[-1])
    assert error_message["type"] == "error"
    assert error_message["data"]["code"] == 4000
    assert error_message["data"]["message"] == "Test error"
    
    # Test connection cleanup on error
    await ws_manager.disconnect(connection_id)
    assert connection_id not in ws_manager.connection_health 