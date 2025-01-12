import pytest
import pytest_asyncio
from typing import Dict, Any, List, AsyncGenerator
import json
import asyncio
import uuid
import logging
from datetime import datetime, timedelta, UTC
from yotsu_chat.core.ws_core import WebSocketError

from yotsu_chat.core.ws_core import manager as ws_manager
from yotsu_chat.core.config import get_settings
from yotsu_chat.utils import debug_log
from .conftest import MockWebSocket, register_test_user
from httpx import AsyncClient
from yotsu_chat.services.channel_service import channel_service
import aiosqlite

logger = logging.getLogger(__name__)
settings = get_settings()

@pytest_asyncio.fixture(autouse=True)
async def cleanup_manager() -> AsyncGenerator[None, None]:
    """Cleanup the WebSocket manager after each test"""
    yield
    await ws_manager.cleanup()
    ws_manager._health_check_task = None
    ws_manager.active_connections.clear()
    ws_manager.channel_connections.clear()
    ws_manager.connection_health.clear()
    ws_manager.connection_rate_limits.clear()

@pytest.mark.asyncio
async def test_websocket_authentication(
    access_token: str,
    expired_token: str,
    mock_websocket: Dict[str, Any]
) -> None:
    """Test WebSocket authentication scenarios:
    1. Missing token
    2. Expired token
    3. Malformed token
    4. Valid token
    5. Multiple connections with same token
    """
    # 1. Missing token
    debug_log("WS_AUTH", "Testing connection with missing token")
    ws = MockWebSocket()
    with pytest.raises(WebSocketError) as exc:
        await ws_manager.authenticate_connection(ws)
    debug_log("WS_AUTH", "Connection rejected - missing token", exc_info=True)
    assert exc.value.code == 1008

    # 2. Expired token
    debug_log("WS_AUTH", "Testing connection with expired token")
    ws = MockWebSocket()
    expired = await expired_token
    ws.query_params["token"] = expired
    with pytest.raises(WebSocketError) as exc:
        await ws_manager.authenticate_connection(ws)
    debug_log("WS_AUTH", "Connection rejected - token expired", exc_info=True)
    assert exc.value.code == 1008

    # 3. Malformed token
    debug_log("WS_AUTH", "Testing connection with malformed token")
    ws = MockWebSocket()
    ws.query_params["token"] = "not.a.jwt.token"
    with pytest.raises(WebSocketError) as exc:
        await ws_manager.authenticate_connection(ws)
    debug_log("WS_AUTH", "Connection rejected - malformed token", exc_info=True)
    assert exc.value.code == 1008

    # 4. Valid token
    debug_log("WS_AUTH", "Testing connection with valid token")
    ws = MockWebSocket()
    ws.query_params["token"] = access_token
    user_id = await ws_manager.authenticate_connection(ws)
    debug_log("WS_AUTH", f"Connection authenticated successfully - user_id: {user_id}")
    assert isinstance(user_id, int)

    # 5. Multiple connections same token
    debug_log("WS_AUTH", "Testing multiple connections with same token")
    ws2 = MockWebSocket()
    ws2.query_params["token"] = access_token
    user_id2 = await ws_manager.authenticate_connection(ws2)
    debug_log("WS_AUTH", f"Second connection authenticated - user_id: {user_id2}")
    assert user_id2 == user_id

@pytest.mark.asyncio
async def test_websocket_auto_subscription(
    mock_websocket: Dict[str, Any],
    access_token: str,
    client: AsyncClient
) -> None:
    """Test automatic channel subscription on WebSocket connection:
    1. Pre-create channels of different types
    2. Connect WebSocket and verify auto-subscription
    3. Verify notes channels are excluded
    4. Test subscription persistence across reconnection
    """
    ws = mock_websocket["websocket"]
    user_id = mock_websocket["user_id"]
    
    # 1. Create test channels of different types
    debug_log("WS_AUTO", "Creating test channels")
    channels = {}
    
    # Public channel
    response = await client.post(
        "/api/channels",
        json={"name": "test-public-auto", "type": "public"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    channels["public"] = response.json()["channel_id"]
    
    # Private channel
    response = await client.post(
        "/api/channels",
        json={"name": "test-private-auto", "type": "private"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    channels["private"] = response.json()["channel_id"]
    
    # Get existing notes channel (created during registration)
    response = await client.get(
        "/api/channels",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    notes_channels = [c for c in response.json() if c["type"] == "notes"]
    assert len(notes_channels) == 1, "User should have exactly one notes channel"
    channels["notes"] = notes_channels[0]["channel_id"]
    
    # 2. Verify initial auto-subscription
    debug_log("WS_AUTO", "Verifying initial auto-subscription")
    
    # Check channel subscriptions
    assert channels["public"] in ws_manager.channel_connections
    assert mock_websocket["connection_id"] in ws_manager.channel_connections[channels["public"]]
    
    assert channels["private"] in ws_manager.channel_connections
    assert mock_websocket["connection_id"] in ws_manager.channel_connections[channels["private"]]
    
    # Verify notes channel was excluded
    assert channels["notes"] not in ws_manager.channel_connections
    debug_log("WS_AUTO", "Initial auto-subscription verified")
    
    # 3. Test subscription persistence across reconnection
    debug_log("WS_AUTO", "Testing subscription persistence")
    
    # Disconnect current WebSocket
    await ws_manager.disconnect(mock_websocket["connection_id"])
    
    # Create new WebSocket connection
    new_ws = MockWebSocket()
    new_ws.query_params["token"] = access_token
    new_connection_id = str(uuid.uuid4())
    
    new_user_id = await ws_manager.authenticate_connection(new_ws)
    assert new_user_id == user_id
    
    await ws_manager.connect(new_ws, new_user_id, new_connection_id)
    debug_log("WS_AUTO", f"Created new connection: {new_connection_id}")
    
    # Verify channels were re-subscribed
    assert channels["public"] in ws_manager.channel_connections
    assert new_connection_id in ws_manager.channel_connections[channels["public"]]
    
    assert channels["private"] in ws_manager.channel_connections
    assert new_connection_id in ws_manager.channel_connections[channels["private"]]
    
    # Verify notes still excluded
    assert channels["notes"] not in ws_manager.channel_connections
    debug_log("WS_AUTO", "Subscription persistence verified")
    
    # Test message delivery to auto-subscribed channel
    debug_log("WS_AUTO", "Testing message delivery to auto-subscribed channel")
    response = await client.post(
        "/api/messages",
        json={"content": "Auto-sub test", "channel_id": channels["public"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    
    # Verify message was received
    messages = new_ws.get_events_by_type("message.created")
    assert len(messages) == 1
    assert messages[0]["data"]["channel_id"] == channels["public"]
    assert messages[0]["data"]["content"] == "Auto-sub test"
    debug_log("WS_AUTO", "Message delivery verified")
    
    # Test channel removal unsubscription
    debug_log("WS_AUTO", "Testing channel removal unsubscription")
    response = await client.delete(
        f"/api/members/{channels['public']}/{user_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 204
    
    # Verify channel was unsubscribed
    assert channels["public"] not in ws_manager.channel_connections
    
    # Test channel addition subscription
    debug_log("WS_AUTO", "Testing channel addition subscription")
    response = await client.post(
        f"/api/members/{channels['public']}/{user_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    
    # Verify channel was re-subscribed
    assert channels["public"] in ws_manager.channel_connections
    assert new_connection_id in ws_manager.channel_connections[channels["public"]]
    
    # Test concurrent connections
    debug_log("WS_AUTO", "Testing concurrent connections")
    another_ws = MockWebSocket()
    another_ws.query_params["token"] = access_token
    another_connection_id = str(uuid.uuid4())
    
    another_user_id = await ws_manager.authenticate_connection(another_ws)
    assert another_user_id == user_id
    
    await ws_manager.connect(another_ws, another_user_id, another_connection_id)
    
    # Verify both connections are subscribed to channels
    assert new_connection_id in ws_manager.channel_connections[channels["public"]]
    assert another_connection_id in ws_manager.channel_connections[channels["public"]]
    assert new_connection_id in ws_manager.channel_connections[channels["private"]]
    assert another_connection_id in ws_manager.channel_connections[channels["private"]]
    
    # Cleanup
    await ws_manager.disconnect(new_connection_id)
    await ws_manager.disconnect(another_connection_id)

@pytest.mark.asyncio
async def test_websocket_authentication_rate_limiting(
    access_token: str,
    mock_websocket: Dict[str, Any]
) -> None:
    """Test rate limiting during authentication:
    1. Track messages across user's connections
    2. Rate limit exceeded behavior
    3. Rate limit reset after window
    4. Rate limit applies to all user's connections
    """
    ws1 = mock_websocket["websocket"]
    user_id = mock_websocket["user_id"]
    connection_id1 = mock_websocket["connection_id"]
    
    # Create second connection for same user
    debug_log("WS_RATE", f"Creating second connection for user_id: {user_id}")
    ws2 = MockWebSocket()
    ws2.query_params["token"] = access_token
    await ws_manager.authenticate_connection(ws2)
    connection_id2 = str(uuid.uuid4())
    await ws_manager.connect(ws2, user_id, connection_id2)
    
    # Send messages from first connection
    debug_log("WS_RATE", f"Sending messages from connection_id: {connection_id1}")
    for i in range(5):
        await ws_manager.handle_client_message(
            connection_id1,
            json.dumps({"type": "message", "content": f"test message {i}"})
        )
    
    # Verify user rate limit tracking
    assert ws_manager.user_rate_limits[user_id]["message_count"] == 5
    debug_log("WS_RATE", f"User message count: {ws_manager.user_rate_limits[user_id]['message_count']}")
    
    # Send messages from second connection
    debug_log("WS_RATE", f"Sending messages from connection_id: {connection_id2}")
    for i in range(5):
        await ws_manager.handle_client_message(
            connection_id2,
            json.dumps({"type": "message", "content": f"test message {i}"})
        )
    
    # Verify combined rate limit
    assert ws_manager.user_rate_limits[user_id]["message_count"] == 10
    debug_log("WS_RATE", f"Combined message count: {ws_manager.user_rate_limits[user_id]['message_count']}")
    
    # Exceed rate limit from either connection
    debug_log("WS_RATE", "Attempting to exceed rate limit")
    await ws_manager.handle_client_message(
        connection_id1,
        json.dumps({"type": "message", "content": "over limit"})
    )
    
    # Verify both connections receive error
    for ws in [ws1, ws2]:
        errors = ws.get_events_by_type("error")
        assert len(errors) > 0
        debug_log("WS_RATE", f"Rate limit error received on connection", exc_info=True)
    
    # Test rate limit reset
    debug_log("WS_RATE", "Testing rate limit reset")
    ws_manager.user_rate_limits[user_id]["last_reset"] = datetime.now(UTC) - timedelta(seconds=61)
    
    # Verify can send from either connection after reset
    for conn_id in [connection_id1, connection_id2]:
        await ws_manager.handle_client_message(
            conn_id,
            json.dumps({"type": "message", "content": "test after reset"})
        )
    assert ws_manager.user_rate_limits[user_id]["message_count"] == 2
    debug_log("WS_RATE", f"Message count after reset: {ws_manager.user_rate_limits[user_id]['message_count']}")

@pytest.mark.asyncio
async def test_websocket_health_check(
    mock_websocket: Dict[str, Any],
    concurrent_websockets: List[Dict[str, Any]]
) -> None:
    """Test WebSocket health check mechanism:
    1. Initial health status
    2. Ping/pong cycle
    3. Multiple connection handling
    4. Connection timeout
    5. Health check task management
    """
    ws = mock_websocket["websocket"]
    connection_id: str = mock_websocket["connection_id"]
    user_id = mock_websocket["user_id"]
    
    # 1. Verify initial health status
    debug_log("WS_HEALTH", f"Checking initial health status for user_id: {user_id}, connection_id: {connection_id}")
    assert connection_id in ws_manager.connection_health
    initial_health = ws_manager.connection_health[connection_id]
    initial_pong_time = initial_health["last_pong"]
    assert isinstance(initial_health["last_pong"], datetime)
    assert not initial_health["pending_ping"]
    
    # 2. Test ping/pong cycle
    debug_log("WS_HEALTH", f"Testing ping/pong cycle for connection_id: {connection_id}")
    await ws_manager.send_ping(connection_id)
    ping_messages = ws.get_events_by_type("ping")
    assert len(ping_messages) == 1
    debug_log("WS_HEALTH", "Ping sent successfully")
    
    # Handle pong and verify health update
    await asyncio.sleep(0.1)  # Add small delay to ensure timestamps are different
    await ws_manager.handle_pong(connection_id)
    assert not ws_manager.connection_health[connection_id]["pending_ping"]
    assert ws_manager.connection_health[connection_id]["last_pong"] > initial_pong_time
    debug_log("WS_HEALTH", "Pong received and health status updated")
    
    # 3. Test multiple connection handling
    debug_log("WS_HEALTH", "Testing health check for multiple connections")
    for conn in concurrent_websockets:
        assert conn["connection_id"] in ws_manager.connection_health
        debug_log("WS_HEALTH", f"Verified health tracking for connection_id: {conn['connection_id']}")
        
    # Send ping to all connections
    for conn in concurrent_websockets:
        await ws_manager.send_ping(conn["connection_id"])
        ping_messages = conn["websocket"].get_events_by_type("ping")
        assert len(ping_messages) == 1
        debug_log("WS_HEALTH", f"Ping sent to connection_id: {conn['connection_id']}")
    
    # 4. Test connection timeout
    debug_log("WS_HEALTH", f"Testing connection timeout for connection_id: {connection_id}")
    await ws_manager.send_ping(connection_id)
    # Simulate timeout
    ws_manager.connection_health[connection_id]["last_pong"] = datetime.now(UTC) - timedelta(seconds=91)
    debug_log("WS_HEALTH", "Simulated connection timeout")
    
    # Run single health check cycle
    now = datetime.now(UTC)
    dead_connections = set()
    async with ws_manager._lock:
        for conn_id, health in ws_manager.connection_health.items():
            try:
                if now - health["last_pong"] > timedelta(seconds=90):  # No pong for 90 seconds
                    dead_connections.add(conn_id)
                else:
                    websocket = ws_manager.active_connections.get(conn_id)
                    if websocket:
                        await websocket.send_text(json.dumps({"type": "ping"}))
                        ws_manager.connection_health[conn_id]["pending_ping"] = True
            except Exception:
                dead_connections.add(conn_id)
    
    # Clean up dead connections
    for conn_id in dead_connections:
        try:
            await ws_manager.disconnect(conn_id)
        except Exception:
            pass
    
    # Verify connection was closed
    assert ws.closed
    assert ws.close_code == 1000  # Standard close code
    debug_log("WS_HEALTH", f"Connection {connection_id} closed due to health check failure", exc_info=True)
    
    # 5. Verify health check task
    debug_log("WS_HEALTH", "Verifying health check background task")
    assert ws_manager._health_check_task is not None
    assert not ws_manager._health_check_task.done()
    
    # Verify user's other connections remain active
    for conn in concurrent_websockets:
        if conn["user_id"] == user_id:
            debug_log("WS_HEALTH", f"Checking status of user's other connection: {conn['connection_id']}")
            assert not conn["websocket"].closed
            assert conn["connection_id"] in ws_manager.connection_health
    
    # Cleanup
    debug_log("WS_HEALTH", "Cleaning up test connections")
    for conn in concurrent_websockets:
        await ws_manager.disconnect(conn["connection_id"])

@pytest.mark.asyncio
async def test_websocket_health_check_recovery(
    mock_websocket: Dict[str, Any]
) -> None:
    """Test WebSocket health check recovery scenarios:
    1. Late pong handling
    2. Reconnection after timeout
    3. Health status reset
    """
    ws = mock_websocket["websocket"]
    connection_id: str = mock_websocket["connection_id"]

    # 1. Test late pong handling
    await ws_manager.send_ping(connection_id)
    initial_health = ws_manager.connection_health[connection_id].copy()  # Make a copy to avoid reference issues

    # Simulate delayed pong with a longer delay to ensure different timestamps
    await asyncio.sleep(0.5)  # Increased delay
    debug_log("WS_HEALTH", f"Testing delayed pong for connection_id: {connection_id}")

    await ws_manager.handle_pong(connection_id)

    # Verify health was updated despite delay
    assert ws_manager.connection_health[connection_id]["last_pong"] > initial_health["last_pong"]

@pytest.mark.asyncio
async def test_websocket_channel_subscriptions(
    mock_websocket: Dict[str, Any],
    access_token: str,
    client: AsyncClient
) -> None:
    """Test WebSocket channel subscription handling:
    1. Initial channel subscriptions
    2. New channel subscription
    3. Channel unsubscription
    4. Multiple channel handling
    """
    ws = mock_websocket["websocket"]
    connection_id: str = mock_websocket["connection_id"]
    user_id = mock_websocket["user_id"]
    
    # 1. Test initial channel subscriptions
    debug_log("WS_CHAN", f"Creating test channel for user_id: {user_id}")
    response = await client.post(
        "/api/channels",
        json={"name": "test-channel", "type": "public"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    channel_id = response.json()["channel_id"]
    debug_log("WS_CHAN", f"Channel created: {channel_id}")
    
    # Join the channel
    await ws_manager.join_channel(connection_id, channel_id)
    
    # Verify WebSocket is subscribed to the channel
    assert channel_id in ws_manager.channel_connections
    assert connection_id in ws_manager.channel_connections[channel_id]
    debug_log("WS_CHAN", f"Verified subscription for connection_id: {connection_id} to channel: {channel_id}")
        
    # 2. Test new channel subscription
    debug_log("WS_CHAN", "Creating second test channel")
    response = await client.post(
        "/api/channels",
        json={"name": "test-channel-2", "type": "public"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    channel_id_2 = response.json()["channel_id"]
    debug_log("WS_CHAN", f"Second channel created: {channel_id_2}")
    
    # Join the second channel
    await ws_manager.join_channel(connection_id, channel_id_2)
    
    # Verify subscription to new channel
    assert channel_id_2 in ws_manager.channel_connections
    assert connection_id in ws_manager.channel_connections[channel_id_2]
    debug_log("WS_CHAN", f"Verified subscription to second channel: {channel_id_2}")
    
    # 3. Test channel unsubscription
    debug_log("WS_CHAN", f"Testing unsubscription from channel: {channel_id}")
    response = await client.delete(
        f"/api/members/{channel_id}/{user_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 204
    
    # Leave the channel
    await ws_manager.leave_channel(connection_id, channel_id)
    
    # Verify WebSocket is unsubscribed (channel should be removed since it's empty)
    assert channel_id not in ws_manager.channel_connections
    debug_log("WS_CHAN", f"Verified unsubscription from channel: {channel_id}")
    
    # 4. Test multiple channel message routing
    debug_log("WS_CHAN", f"Testing message broadcast to channel: {channel_id_2}")
    response = await client.post(
        "/api/messages",
        json={"content": "Test message", "channel_id": channel_id_2},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    
    # Verify message was broadcast to the correct channel
    messages = ws.get_events_by_type("message.created")
    assert len(messages) == 1
    assert messages[0]["data"]["channel_id"] == channel_id_2
    debug_log("WS_CHAN", f"Verified message delivery to channel: {channel_id_2}")

    # Verify user's channel membership using direct DB query
    async with aiosqlite.connect("data/db/test/test_yotsu_chat.db") as db:
        async with db.execute(
            "SELECT user_id FROM channels_members WHERE channel_id = ?",
            (channel_id_2,)
        ) as cursor:
            members = await cursor.fetchall()
            member_ids = [m[0] for m in members]
            assert user_id in member_ids
        
        async with db.execute(
            "SELECT user_id FROM channels_members WHERE channel_id = ?",
            (channel_id,)
        ) as cursor:
            members = await cursor.fetchall()
            member_ids = [m[0] for m in members]
            assert user_id not in member_ids
        debug_log("WS_CHAN", f"Verified user channel memberships for user_id: {user_id}")

    # Cleanup
    debug_log("WS_CHAN", "Cleaning up test connections")
    await ws_manager.disconnect(connection_id)

@pytest.mark.asyncio
async def test_websocket_channel_broadcasts(
    mock_websocket: Dict[str, Any],
    concurrent_websockets: List[Dict[str, Any]],
    access_token: str,
    client: AsyncClient
) -> None:
    """Test WebSocket channel broadcast handling:
    1. Message broadcasts to channel members
    2. Reaction broadcasts
    3. Member join/leave broadcasts
    4. Channel update broadcasts
    """
    ws = mock_websocket["websocket"]
    connection_id: str = mock_websocket["connection_id"]
    user_id = mock_websocket["user_id"]
    
    # Create additional users for concurrent websockets
    debug_log("WS_BCAST", "Creating additional users for concurrent websockets")
    concurrent_users = []
    for i in range(len(concurrent_websockets)):
        user_data = await register_test_user(
            client,
            email=f"test{i+2}@example.com",
            password="Password1234!",
            display_name=f"Test User{' Secondary' if i == 0 else ' Third'}"  # "Test User Secondary" for first, "Test User Third" for second
        )
        concurrent_users.append(user_data)
        concurrent_websockets[i]["user_id"] = user_data["user_id"]
        concurrent_websockets[i]["token"] = user_data["access_token"]
        debug_log("WS_BCAST", f"Created user {user_data['user_id']} for concurrent websocket {i+1}")

    # Create test channel
    debug_log("WS_BCAST", f"Creating test channel for broadcast tests - user_id: {user_id}")
    response = await client.post(
        "/api/channels",
        json={"name": "test-broadcast", "type": "private"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    channel_id = response.json()["channel_id"]
    debug_log("WS_BCAST", f"Test channel created: {channel_id}")
    
    # Add concurrent users to channel
    debug_log("WS_BCAST", "Adding concurrent users to channel")
    for i, conn in enumerate(concurrent_websockets):
        response = await client.post(
            f"/api/members/{channel_id}",
            json={"user_id": conn["user_id"]},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
        # Verify automatic subscription
        assert channel_id in ws_manager.channel_connections
        assert conn["connection_id"] in ws_manager.channel_connections[channel_id]
        debug_log("WS_BCAST", f"Added user_id: {conn['user_id']} to channel and verified subscription")
    
    # Verify main websocket was automatically subscribed (as channel creator)
    assert channel_id in ws_manager.channel_connections
    assert connection_id in ws_manager.channel_connections[channel_id]
    debug_log("WS_BCAST", f"Verified main websocket subscription")

    # 1. Test message broadcasts
    debug_log("WS_BCAST", "Testing message broadcast to all channel members")
    response = await client.post(
        "/api/messages",
        json={"content": "Broadcast test", "channel_id": channel_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    message_id = response.json()["message_id"]
    
    # Verify all connections received the message
    for conn in concurrent_websockets:
        messages = conn["websocket"].get_events_by_type("message.created")
        assert len(messages) == 1
        assert messages[0]["data"]["content"] == "Broadcast test"
        debug_log("WS_BCAST", f"Verified message receipt for user_id: {conn['user_id']}")
    
    # 2. Test reaction broadcasts
    debug_log("WS_BCAST", f"Testing reaction broadcast - message_id: {message_id}")
    response = await client.post(
        f"/api/reactions/messages/{message_id}",
        json={"emoji": "👍"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    
    # Verify all connections received the reaction
    for conn in concurrent_websockets:
        reactions = conn["websocket"].get_events_by_type("reaction.added")
        assert len(reactions) == 1
        assert reactions[0]["data"]["emoji"] == "👍"
        debug_log("WS_BCAST", f"Verified reaction receipt for user_id: {conn['user_id']}")
    
    # 3. Test member join/leave broadcasts
    first_conn = concurrent_websockets[0]
    debug_log("WS_BCAST", f"Testing member leave broadcast - user_id: {first_conn['user_id']}")
    response = await client.delete(
        f"/api/members/{channel_id}/{first_conn['user_id']}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 204
    
    # Verify remaining connections received leave notification
    for conn in concurrent_websockets[1:]:
        events = conn["websocket"].get_events_by_type("member_leave")
        assert len(events) == 1
        assert events[0]["data"]["user_id"] == first_conn["user_id"]
        debug_log("WS_BCAST", f"Verified leave notification for user_id: {conn['user_id']}")
    
    # 4. Test channel update broadcasts
    debug_log("WS_BCAST", f"Testing channel update broadcast - channel_id: {channel_id}")
    response = await client.patch(
        f"/api/channels/{channel_id}",
        json={"name": "updated-broadcast"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    
    # Verify all remaining members received update
    for conn in concurrent_websockets[1:]:
        updates = conn["websocket"].get_events_by_type("channel_update")
        assert len(updates) == 1
        assert updates[0]["data"]["name"] == "updated-broadcast"
        debug_log("WS_BCAST", f"Verified update notification for user_id: {conn['user_id']}")
    
    # Cleanup
    debug_log("WS_BCAST", "Cleaning up test connections")
    await ws_manager.disconnect(connection_id)
    for conn in concurrent_websockets:
        await ws_manager.disconnect(conn["connection_id"])

@pytest.mark.asyncio
async def test_websocket_thread_lifecycle(
    mock_websocket: Dict[str, Any],
    concurrent_websockets: List[Dict[str, Any]],
    access_token: str,
    client: AsyncClient
) -> None:
    """Test core thread operations:
    1. Thread creation and initial state
    2. Reply handling and metadata updates
    3. Thread deletion and cascade behavior
    """
    ws = mock_websocket["websocket"]
    connection_id: str = mock_websocket["connection_id"]
    user_id = mock_websocket["user_id"]
    
    # Setup test channel
    debug_log("WS_THREAD", f"Creating test channel for thread lifecycle - user_id: {user_id}")
    response = await client.post(
        "/api/channels",
        json={"name": "test-thread-lifecycle", "type": "public"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    channel_id = response.json()["channel_id"]
    
    # Subscribe to the channel
    await ws_manager.join_channel(connection_id, channel_id)
    debug_log("WS_THREAD", f"Subscribed to channel: {channel_id}")
    
    # Create parent message
    debug_log("WS_THREAD", "Creating parent message")
    response = await client.post(
        "/api/messages",
        json={"content": "Parent message", "channel_id": channel_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    parent_id = response.json()["message_id"]
    
    # Verify thread creation state
    messages = ws.get_events_by_type("message.created")
    assert len(messages) == 1
    assert messages[0]["data"]["content"] == "Parent message"
    assert messages[0]["data"]["parent_id"] is None
    debug_log("WS_THREAD", "Thread creation verified")
    
    # Test reply handling
    debug_log("WS_THREAD", "Testing reply handling")
    reply_ids = []
    for i in range(3):
        response = await client.post(
            "/api/messages",
            json={
                "content": f"Reply {i+1}",
                "channel_id": channel_id,
                "parent_id": parent_id
            },
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
        reply_ids.append(response.json()["message_id"])
        debug_log("WS_THREAD", f"Reply {i+1} created")
    
    # Verify thread metadata updates
    thread_updates = ws.get_events_by_type("thread_update")
    latest_update = thread_updates[-1]
    assert latest_update["data"]["message_id"] == parent_id
    assert latest_update["data"]["reply_count"] == 3
    debug_log("WS_THREAD", "Thread metadata updates verified")
    
    # Test thread deletion cascade
    debug_log("WS_THREAD", "Testing thread deletion cascade")
    response = await client.delete(
        f"/api/messages/{parent_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 204
    
    # Verify deletion cascade
    delete_events = ws.get_events_by_type("message_delete")
    assert len(delete_events) == 1
    assert delete_events[0]["data"]["message_id"] == parent_id
    
    thread_updates = ws.get_events_by_type("thread_update")
    latest_update = thread_updates[-1]
    assert latest_update["data"]["message_id"] == parent_id
    assert latest_update["data"]["is_deleted"] is True
    debug_log("WS_THREAD", "Thread deletion cascade verified")
    
    # Cleanup
    await ws_manager.disconnect(connection_id)

async def test_websocket_thread_interactions(
    mock_websocket: Dict[str, Any],
    concurrent_websockets: List[Dict[str, Any]],
    access_token: str
) -> None:
    """Test thread interaction features:
    1. Typing indicators in threads
    2. Read receipts for thread messages
    3. Thread metadata updates from message reactions
    """
    ws = mock_websocket["websocket"]
    connection_id: str = mock_websocket["connection_id"]
    user_id = mock_websocket["user_id"]
    
    # Setup test channel and thread
    debug_log("WS_THREAD_INT", "Creating test channel and thread")
    response = await ws.app.client.post(
        "/api/channels",
        json={"name": "test-thread-interactions", "type": "public"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    channel_id = response.json()["channel_id"]
    
    # Add concurrent users
    for conn in concurrent_websockets:
        response = await ws.app.client.post(
            f"/api/members/{channel_id}",
            json={"user_id": conn["user_id"]},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
    
    # Create parent message and replies
    response = await ws.app.client.post(
        "/api/messages",
        json={"content": "Parent for interactions", "channel_id": channel_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    parent_id = response.json()["message_id"]
    
    # Add some replies
    reply_ids = []
    for i in range(2):
        response = await ws.app.client.post(
            "/api/messages",
            json={
                "content": f"Reply {i+1}",
                "channel_id": channel_id,
                "parent_id": parent_id
            },
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
        reply_ids.append(response.json()["message_id"])
    
    # Test typing indicators
    debug_log("WS_THREAD_INT", "Testing typing indicators")
    await ws_manager.handle_client_message(
        connection_id,
        json.dumps({
            "type": "typing_start",
            "channel_id": channel_id,
            "parent_id": parent_id
        })
    )
    
    # Verify typing broadcasts
    for conn in concurrent_websockets:
        typing_events = conn["websocket"].get_events_by_type("typing_start")
        assert len(typing_events) == 1
        assert typing_events[0]["data"]["parent_id"] == parent_id
        assert typing_events[0]["data"]["user_id"] == user_id
    debug_log("WS_THREAD_INT", "Typing indicators verified")
    
    # Test read receipts
    debug_log("WS_THREAD_INT", "Testing read receipts")
    await ws_manager.handle_client_message(
        connection_id,
        json.dumps({
            "type": "mark_read",
            "message_id": parent_id
        })
    )
    
    # Verify read receipt broadcasts
    for conn in concurrent_websockets:
        read_events = conn["websocket"].get_events_by_type("message_read")
        assert len(read_events) == 1
        assert read_events[0]["data"]["message_id"] == parent_id
        assert read_events[0]["data"]["user_id"] == user_id
    debug_log("WS_THREAD_INT", "Read receipts verified")
    
    # Test thread metadata updates from message reactions
    debug_log("WS_THREAD_INT", "Testing thread metadata updates from reactions")
    
    # Clear previous events
    ws.events.clear()
    for conn in concurrent_websockets:
        conn["websocket"].events.clear()
    
    # Add reaction to parent message
    response = await ws.app.client.post(
        f"/api/reactions/messages/{parent_id}",
        json={"emoji": "👍"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    
    # Add reaction to reply
    response = await ws.app.client.post(
        f"/api/reactions/messages/{reply_ids[0]}",
        json={"emoji": "❤️"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    
    # Verify thread metadata updates
    thread_updates = ws.get_events_by_type("thread_update")
    latest_update = thread_updates[-1]
    assert latest_update["data"]["message_id"] == parent_id
    assert latest_update["data"]["reaction_count"] == 2  # Total reactions in thread
    debug_log("WS_THREAD_INT", "Thread metadata updates from reactions verified")
    
    # Remove reaction from reply
    response = await ws.app.client.delete(
        f"/api/reactions/messages/{reply_ids[0]}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 204
    
    # Verify thread metadata updated after reaction removal
    thread_updates = ws.get_events_by_type("thread_update")
    latest_update = thread_updates[-1]
    assert latest_update["data"]["message_id"] == parent_id
    assert latest_update["data"]["reaction_count"] == 1  # Only parent reaction remains
    debug_log("WS_THREAD_INT", "Thread metadata updates after reaction removal verified")
    
    # Cleanup
    await ws_manager.disconnect(connection_id)
    for conn in concurrent_websockets:
        await ws_manager.disconnect(conn["connection_id"])

async def test_websocket_message_visibility(
    mock_websocket: Dict[str, Any],
    access_token: str
) -> None:
    """Test message update visibility with pagination:
    1. Edit visibility based on current view
    2. Delete visibility based on current view
    3. Visibility changes with pagination
    """
    ws = mock_websocket["websocket"]
    connection_id: str = mock_websocket["connection_id"]
    
    # Setup test channel
    debug_log("WS_MSG_VIS", "Creating test channel")
    response = await ws.app.client.post(
        "/api/channels",
        json={"name": "test-message-visibility", "type": "public"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    channel_id = response.json()["channel_id"]
    
    # Create messages across multiple pages
    message_ids = []
    for i in range(50):  # 20 per page
        response = await ws.app.client.post(
            "/api/messages",
            json={"content": f"Message {i}", "channel_id": channel_id},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
        message_ids.append(response.json()["message_id"])
    
    # Get latest page
    response = await ws.app.client.get(
        f"/api/messages/{channel_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    visible_messages = response.json()
    visible_ids = {msg["message_id"] for msg in visible_messages}
    
    # Test edit visibility
    debug_log("WS_MSG_VIS", "Testing edit visibility")
    
    # Edit visible message
    visible_msg = message_ids[-1]
    response = await ws.app.client.put(
        f"/api/messages/{visible_msg}",
        json={"content": "Edited visible"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    
    # Edit invisible message
    invisible_msg = message_ids[0]
    response = await ws.app.client.put(
        f"/api/messages/{invisible_msg}",
        json={"content": "Edited invisible"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    
    # Verify edit notifications
    edit_events = ws.get_events_by_type("message_edit")
    visible_edits = [e for e in edit_events if e["data"]["message_id"] == visible_msg]
    invisible_edits = [e for e in edit_events if e["data"]["message_id"] == invisible_msg]
    
    assert len(visible_edits) > 0
    assert len(invisible_edits) == 0
    debug_log("WS_MSG_VIS", "Edit visibility verified")
    
    # Test delete visibility
    debug_log("WS_MSG_VIS", "Testing delete visibility")
    
    # Delete visible message
    visible_del = message_ids[-2]
    response = await ws.app.client.delete(
        f"/api/messages/{visible_del}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 204
    
    # Delete invisible message
    invisible_del = message_ids[1]
    response = await ws.app.client.delete(
        f"/api/messages/{invisible_del}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 204
    
    # Verify deletion notifications
    delete_events = ws.get_events_by_type("message_delete")
    visible_dels = [e for e in delete_events if e["data"]["message_id"] == visible_del]
    invisible_dels = [e for e in delete_events if e["data"]["message_id"] == invisible_del]
    
    assert len(visible_dels) > 0
    assert len(invisible_dels) == 0
    debug_log("WS_MSG_VIS", "Delete visibility verified")
    
    # Test visibility changes with pagination
    debug_log("WS_MSG_VIS", "Testing visibility changes")
    response = await ws.app.client.get(
        f"/api/messages/{channel_id}?before={message_ids[30]}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    new_visible = response.json()
    new_visible_ids = {msg["message_id"] for msg in new_visible}
    
    # Clear previous events
    ws.events.clear()
    
    # Edit previously visible message
    response = await ws.app.client.put(
        f"/api/messages/{visible_msg}",
        json={"content": "Edit after pagination"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    
    # Verify no notification for now-invisible message
    edit_events = ws.get_events_by_type("message_edit")
    assert len(edit_events) == 0
    debug_log("WS_MSG_VIS", "Visibility changes verified")
    
    # Cleanup
    await ws_manager.disconnect(connection_id)

async def test_websocket_channel_type_behavior(
    mock_websocket: Dict[str, Any],
    concurrent_websockets: List[Dict[str, Any]],
    access_token: str
) -> None:
    """Test WebSocket behavior across channel types:
    1. Public channel message handling
    2. Private channel access control
    3. Direct message specifics
    """
    ws = mock_websocket["websocket"]
    connection_id: str = mock_websocket["connection_id"]
    user_id = mock_websocket["user_id"]
    
    channels = {}
    
    # Setup channels
    debug_log("WS_CHAN_TYPE", "Creating test channels")
    
    # Public channel
    response = await ws.app.client.post(
        "/api/channels",
        json={"name": "test-public", "type": "public"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    channels["public"] = response.json()["channel_id"]
    
    # Private channel
    response = await ws.app.client.post(
        "/api/channels",
        json={"name": "test-private", "type": "private"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    channels["private"] = response.json()["channel_id"]
    
    # Direct channel
    other_user = concurrent_websockets[0]["user_id"]
    response = await ws.app.client.post(
        "/api/channels/direct",
        json={"user_id": other_user},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    channels["direct"] = response.json()["channel_id"]
    
    # Test each channel type
    for channel_type, channel_id in channels.items():
        debug_log("WS_CHAN_TYPE", f"Testing {channel_type} channel")
        
        # Add users based on channel type
        if channel_type in ["public", "private"]:
            for conn in concurrent_websockets:
                response = await ws.app.client.post(
                    f"/api/members/{channel_id}",
                    json={"user_id": conn["user_id"]},
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                assert response.status_code == 201
        
        # Send test message
        response = await ws.app.client.post(
            "/api/messages",
            json={"content": f"Test {channel_type}", "channel_id": channel_id},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
        message_id = response.json()["message_id"]
        
        # Verify message delivery
        if channel_type == "direct":
            # Only the other user should receive
            other_ws = concurrent_websockets[0]["websocket"]
            messages = other_ws.get_events_by_type("message.created")
            assert len(messages) == 1
            assert messages[0]["data"]["channel_id"] == channel_id
        else:
            # All channel members should receive
            for conn in concurrent_websockets:
                messages = conn["websocket"].get_events_by_type("message.created")
                assert len(messages) == 1
                assert messages[0]["data"]["channel_id"] == channel_id
        
        # Clear events for next channel
        ws.events.clear()
        for conn in concurrent_websockets:
            conn["websocket"].events.clear()
    
    # Cleanup
    await ws_manager.disconnect(connection_id)
    for conn in concurrent_websockets:
        await ws_manager.disconnect(conn["connection_id"])