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
    ws_manager.subscription_groups.clear()
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
    second_user_token: Dict[str, Any],
    client: AsyncClient
) -> None:
    """Test automatic channel subscription on WebSocket connection:
    1. Pre-create channels of different types
    2. Connect WebSocket and verify auto-subscription to all channels
    3. Test subscription persistence across reconnection
    4. Test unsubscription on removal
    5. Test auto-subscription on channel addition
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
    
    # Check channel subscriptions for all channel types
    assert channels["public"] in ws_manager.subscription_groups
    assert mock_websocket["connection_id"] in ws_manager.subscription_groups[channels["public"]]
    
    assert channels["private"] in ws_manager.subscription_groups
    assert mock_websocket["connection_id"] in ws_manager.subscription_groups[channels["private"]]
    
    # Verify notes channel is included
    assert channels["notes"] in ws_manager.subscription_groups
    assert mock_websocket["connection_id"] in ws_manager.subscription_groups[channels["notes"]]
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
    
    # Verify channels were re-subscribed (including notes)
    assert channels["public"] in ws_manager.subscription_groups
    assert new_connection_id in ws_manager.subscription_groups[channels["public"]]
    
    assert channels["private"] in ws_manager.subscription_groups
    assert new_connection_id in ws_manager.subscription_groups[channels["private"]]
    
    assert channels["notes"] in ws_manager.subscription_groups
    assert new_connection_id in ws_manager.subscription_groups[channels["notes"]]
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
    assert channels["public"] not in ws_manager.subscription_groups
    
    # Create a new channel for testing addition subscription
    debug_log("WS_AUTO", "Creating new channel for addition subscription test")
    response = await client.post(
        "/api/channels",
        json={"name": "test-addition-auto", "type": "private"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    addition_channel_id = response.json()["channel_id"]
    
    # Test channel addition subscription
    debug_log("WS_AUTO", "Testing channel addition subscription")
    response = await client.post(
        f"/api/members/{addition_channel_id}",
        json={"user_id": second_user_token["user_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    
    # Verify channel was auto-subscribed
    assert addition_channel_id in ws_manager.subscription_groups
    assert new_connection_id in ws_manager.subscription_groups[addition_channel_id]
    
    # Cleanup
    await ws_manager.disconnect(new_connection_id)

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
        errors = ws.get_events_by_type("system.error")
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
    await ws_manager.subscribe_to_updates(connection_id, channel_id)
    
    # Verify WebSocket is subscribed to the channel
    assert channel_id in ws_manager.subscription_groups
    assert connection_id in ws_manager.subscription_groups[channel_id]
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
    await ws_manager.subscribe_to_updates(connection_id, channel_id_2)
    
    # Verify subscription to new channel
    assert channel_id_2 in ws_manager.subscription_groups
    assert connection_id in ws_manager.subscription_groups[channel_id_2]
    debug_log("WS_CHAN", f"Verified subscription to second channel: {channel_id_2}")
    
    # 3. Test channel unsubscription
    debug_log("WS_CHAN", f"Testing unsubscription from channel: {channel_id}")
    response = await client.delete(
        f"/api/members/{channel_id}/{user_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 204
    
    # Leave the channel
    await ws_manager.unsubscribe_from_updates(connection_id, channel_id)
    
    # Verify WebSocket is unsubscribed (channel should be removed since it's empty)
    assert channel_id not in ws_manager.subscription_groups
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
    client: AsyncClient,
    concurrent_websockets: List[Dict[str, Any]],
    access_token: str
):
    """Test WebSocket channel broadcast handling:
    1. Message broadcasts to channel members (created, updated, deleted)
    2. Reaction broadcasts (added, removed)
    3. Member broadcasts (joined, left)
    4. Channel update broadcasts
    5. Role update broadcasts
    """
    # Setup main test user's WebSocket first
    debug_log("WS_BROADCAST", "Setting up main test user's WebSocket")
    ws = MockWebSocket()
    ws.query_params["token"] = access_token
    connection_id = str(uuid.uuid4())
    user_id = await ws_manager.authenticate_connection(ws)
    await ws_manager.connect(ws, user_id, connection_id)
    debug_log("WS_BROADCAST", "Main test user's WebSocket connected")

    # Create test channel
    debug_log("WS_BROADCAST", "Creating test channel")
    response = await client.post(
        "/api/channels",
        json={"name": "test-broadcast", "type": "private"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    channel_id = response.json()["channel_id"]
    debug_log("WS_BROADCAST", f"Created channel {channel_id}")

    # Debug subscription state
    debug_log("WS_BROADCAST", f"Subscription state after channel creation:")
    debug_log("WS_BROADCAST", f"├─ Channel ID: {channel_id}")
    debug_log("WS_BROADCAST", f"├─ Subscription groups: {ws_manager.subscription_groups}")
    debug_log("WS_BROADCAST", f"├─ Active connections: {list(ws_manager.active_connections.keys())}")
    debug_log("WS_BROADCAST", f"└─ Connection users: {ws_manager.connection_users}")

    # Verify channel.init event on creator's WebSocket
    init_events = ws.get_events_by_type("channel.init")
    debug_log("WS_BROADCAST", f"Creator's WebSocket has {len(init_events)} channel.init events")
    if len(init_events) > 0:
        debug_log("WS_BROADCAST", f"First event data: {init_events[0]['data']}")
    assert len(init_events) == 1
    init_data = init_events[0]["data"]
    assert init_data["channel_id"] == channel_id
    assert init_data["name"] == "test-broadcast"
    assert init_data["type"] == "private"
    assert isinstance(init_data["members"], list)
    # Should have one member (the creator) initially
    assert len(init_data["members"]) == 1
    creator = init_data["members"][0]
    assert "user_id" in creator
    assert "display_name" in creator
    assert "role" in creator  # Private channel, so role should be present
    assert creator["role"] == "owner"

    # Clear events after channel creation
    ws.events.clear()
    for conn in concurrent_websockets:
        conn["websocket"].events.clear()

    # Add concurrent users to channel
    for user in concurrent_websockets:
        response = await client.post(
            f"/api/members/{channel_id}",
            json={"user_id": user["user_id"]},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
        
        # Verify member.joined event for subsequent additions
        for conn in concurrent_websockets:
            events = conn["websocket"].get_events_by_type("member.joined")
            assert len(events) > 0
            latest_event = events[-1]
            assert latest_event["data"]["user_id"] == user["user_id"]
            assert latest_event["data"]["channel_id"] == channel_id
            assert "display_name" in latest_event["data"]
            assert "role" in latest_event["data"]  # Private channel, so role should be present
        
        # Verify automatic subscription
        assert channel_id in ws_manager.subscription_groups
        assert user["connection_id"] in ws_manager.subscription_groups[channel_id]

    # Clear previous events
    for conn in concurrent_websockets:
        conn["websocket"].events.clear()

    # 1. Test message broadcasts
    # Create message
    response = await client.post(
        "/api/messages",
        json={"content": "Broadcast test", "channel_id": channel_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    message_id = response.json()["message_id"]
    
    # Verify message.created event
    for conn in concurrent_websockets:
        messages = conn["websocket"].get_events_by_type("message.created")
        assert len(messages) == 1
        assert messages[0]["data"]["content"] == "Broadcast test"
    
    # Test message update
    response = await client.put(
        f"/api/messages/{message_id}",
        json={"content": "Updated broadcast test"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    
    # Verify message.updated event
    for conn in concurrent_websockets:
        updates = conn["websocket"].get_events_by_type("message.updated")
        assert len(updates) == 1
        assert updates[0]["data"]["content"] == "Updated broadcast test"
        assert updates[0]["data"]["message_id"] == message_id
    
    # 2. Test reaction broadcasts
    # Add reaction
    response = await client.post(
        f"/api/reactions/messages/{message_id}",
        json={"emoji": "👍"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    
    # Verify reaction.added event
    for conn in concurrent_websockets:
        reactions = conn["websocket"].get_events_by_type("reaction.added")
        assert len(reactions) == 1
        assert reactions[0]["data"]["emoji"] == "👍"
    
    # Remove reaction
    response = await client.delete(
        f"/api/reactions/messages/{message_id}?emoji=👍",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 204
    
    # Verify reaction.removed event
    for conn in concurrent_websockets:
        removals = conn["websocket"].get_events_by_type("reaction.removed")
        assert len(removals) == 1
        assert removals[0]["data"]["message_id"] == message_id
        assert removals[0]["data"]["emoji"] == "👍"
    
    # 3. Test role update broadcast
    first_conn = concurrent_websockets[0]
    response = await client.put(
        f"/api/members/{channel_id}/{first_conn['user_id']}/role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    
    # Verify role.update event
    for conn in concurrent_websockets:
        updates = conn["websocket"].get_events_by_type("role.update")
        assert len(updates) == 1
        assert updates[0]["data"]["user_id"] == first_conn["user_id"]
        assert updates[0]["data"]["role"] == "admin"
        assert updates[0]["data"]["channel_id"] == channel_id
    
    # 4. Test member leave broadcast
    response = await client.delete(
        f"/api/members/{channel_id}/{first_conn['user_id']}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 204
    
    # Verify member.left event
    for conn in concurrent_websockets[1:]:
        events = conn["websocket"].get_events_by_type("member.left")
        assert len(events) == 1
        assert events[0]["data"]["user_id"] == first_conn["user_id"]
        assert events[0]["data"]["channel_id"] == channel_id
    
    # 5. Test message deletion broadcast
    response = await client.delete(
        f"/api/messages/{message_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 204
    
    # Verify message.deleted event
    for conn in concurrent_websockets[1:]:  # Skip first connection as they left
        deletes = conn["websocket"].get_events_by_type("message.deleted")
        assert len(deletes) == 1
        assert deletes[0]["data"]["message_id"] == message_id
        assert deletes[0]["data"]["channel_id"] == channel_id
        assert deletes[0]["data"]["is_deleted"] is False
    
    # 6. Test channel update broadcast
    response = await client.patch(
        f"/api/channels/{channel_id}",
        json={"name": "updated-broadcast"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    
    # Verify channel.update event
    for conn in concurrent_websockets[1:]:
        updates = conn["websocket"].get_events_by_type("channel.update")
        assert len(updates) == 1
        assert updates[0]["data"]["name"] == "updated-broadcast"
        assert updates[0]["data"]["channel_id"] == channel_id
    
    # Cleanup
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
    1. Thread creation (parent message)
    2. Reply handling
    3. Message updates (parent and replies)
    4. Thread deletion cascade:
       - Soft delete parent with replies
       - Delete replies
       - Hard delete parent when no replies remain
    """
    ws = mock_websocket["websocket"]
    connection_id: str = mock_websocket["connection_id"]
    user_id = mock_websocket["user_id"]
    
    # Setup main test user's WebSocket first
    ws = MockWebSocket()
    ws.query_params["token"] = access_token
    connection_id = str(uuid.uuid4())
    user_id = await ws_manager.authenticate_connection(ws)
    await ws_manager.connect(ws, user_id, connection_id)
    debug_log("WS_THREAD", "Main test user's WebSocket connected")

    # Create test channel
    response = await client.post(
        "/api/channels",
        json={"name": "test-thread-lifecycle", "type": "public"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    channel_id = response.json()["channel_id"]
    debug_log("WS_THREAD", f"Created test channel {channel_id}")

    # Add concurrent users to channel
    for user in concurrent_websockets:
        response = await client.post(
            f"/api/members/{channel_id}",
            json={"user_id": user["user_id"]},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
        debug_log("WS_THREAD", f"Added user {user['user_id']} to channel")

    # Clear any previous events
    ws.events.clear()
    for conn in concurrent_websockets:
        conn["websocket"].events.clear()
    debug_log("WS_THREAD", "Cleared previous events")

    # Debug subscription state
    debug_log("WS_THREAD", f"Subscription state before creating message:")
    debug_log("WS_THREAD", f"├─ Channel ID: {channel_id}")
    debug_log("WS_THREAD", f"├─ Main connection ID: {connection_id}")
    debug_log("WS_THREAD", f"├─ Subscription groups: {ws_manager.subscription_groups}")
    debug_log("WS_THREAD", f"├─ Active connections: {list(ws_manager.active_connections.keys())}")
    debug_log("WS_THREAD", f"└─ Connection users: {ws_manager.connection_users}")

    # 1. Create parent message
    debug_log("WS_THREAD", "Creating parent message")
    response = await client.post(
        "/api/messages",
        json={"content": "Parent message", "channel_id": channel_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    parent_id = response.json()["message_id"]
    
    # Verify parent message creation
    for receiver in [ws, *[c["websocket"] for c in concurrent_websockets]]:
        messages = receiver.get_events_by_type("message.created")
        assert len(messages) == 1
        message_data = messages[0]["data"]
        assert message_data["content"] == "Parent message"
        assert message_data["message_id"] == parent_id
        assert message_data["user_id"] == user_id
        assert message_data["channel_id"] == channel_id
        assert "created_at" in message_data
        assert message_data["parent_id"] is None  # parent_id is included but null
    debug_log("WS_THREAD", "Parent message creation verified")
    
    # 2. Test reply handling
    debug_log("WS_THREAD", "Testing reply handling")
    reply_ids = []
    
    # Add replies from different users
    for i, conn in enumerate(concurrent_websockets):
        response = await client.post(
            "/api/messages",
            json={
                "content": f"Reply {i+1}",
                "channel_id": channel_id,
                "parent_id": parent_id
            },
            headers={"Authorization": f"Bearer {conn['token']}"}
        )
        assert response.status_code == 201
        reply_ids.append(response.json()["message_id"])
        
        # Verify reply creation
        for receiver in [ws, *[c["websocket"] for c in concurrent_websockets]]:
            messages = receiver.get_events_by_type("message.created")
            latest_message = messages[-1]
            message_data = latest_message["data"]
            assert message_data["content"] == f"Reply {i+1}"
            assert message_data["message_id"] == reply_ids[-1]
            assert message_data["user_id"] == conn["user_id"]
            assert message_data["channel_id"] == channel_id
            assert message_data["parent_id"] == parent_id
            assert "created_at" in message_data
        debug_log("WS_THREAD", f"Reply {i+1} creation verified")
    
    # 3. Test message updates
    debug_log("WS_THREAD", "Testing message updates")
    
    # Update parent message
    response = await client.put(
        f"/api/messages/{parent_id}",
        json={"content": "Updated parent message"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    
    # Verify parent update
    for receiver in [ws, *[c["websocket"] for c in concurrent_websockets]]:
        updates = receiver.get_events_by_type("message.updated")
        assert len(updates) == 1
        update_data = updates[0]["data"]
        assert update_data["message_id"] == parent_id
        assert update_data["content"] == "Updated parent message"
        assert "updated_at" in update_data
    
    # Update a reply
    first_reply_id = reply_ids[0]
    response = await client.put(
        f"/api/messages/{first_reply_id}",
        json={"content": "Updated reply"},
        headers={"Authorization": f"Bearer {concurrent_websockets[0]['token']}"}
    )
    assert response.status_code == 200
    
    # Verify reply update
    for receiver in [ws, *[c["websocket"] for c in concurrent_websockets]]:
        updates = receiver.get_events_by_type("message.updated")
        latest_update = updates[-1]
        update_data = latest_update["data"]
        assert update_data["message_id"] == first_reply_id
        assert update_data["content"] == "Updated reply"
        assert "updated_at" in update_data
    
    # 4. Test thread deletion cascade
    debug_log("WS_THREAD", "Testing thread deletion cascade")
    
    # Delete parent with replies (should soft delete)
    response = await client.delete(
        f"/api/messages/{parent_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 204
    
    # Verify soft delete event
    for receiver in [ws, *[c["websocket"] for c in concurrent_websockets]]:
        soft_deletes = receiver.get_events_by_type("message.deleted")
        assert len(soft_deletes) == 1
        delete_data = soft_deletes[0]["data"]
        assert delete_data["message_id"] == parent_id
        assert delete_data["channel_id"] == channel_id
        assert delete_data["is_deleted"] is True
    debug_log("WS_THREAD", "Parent soft deletion verified")
    
    # Delete all replies and verify parent hard deletion
    for i, reply_id in enumerate(reply_ids):
        # Use the reply author's token
        author_token = concurrent_websockets[i]['token']
        response = await client.delete(
            f"/api/messages/{reply_id}",
            headers={"Authorization": f"Bearer {author_token}"}
        )
        assert response.status_code == 204
        
        # For all replies except the last one, verify message.deleted event
        if i < len(reply_ids) - 1:
            for receiver in [ws, *[c["websocket"] for c in concurrent_websockets]]:
                deletes = receiver.get_events_by_type("message.deleted")
                latest_delete = deletes[-1]
                delete_data = latest_delete["data"]
                assert delete_data["message_id"] == reply_id
                assert delete_data["channel_id"] == channel_id
                assert delete_data["is_deleted"] is False
        else:
            # For the last reply, verify parent hard deletion
            for receiver in [ws, *[c["websocket"] for c in concurrent_websockets]]:
                deletes = receiver.get_events_by_type("message.deleted")
                latest_delete = deletes[-1]
                delete_data = latest_delete["data"]
                assert delete_data["message_id"] == parent_id
                assert delete_data["channel_id"] == channel_id
                assert delete_data["is_deleted"] is False
    
    debug_log("WS_THREAD", "Thread deletion cascade verified")
    
    # Cleanup
    await ws_manager.disconnect(connection_id)
    for conn in concurrent_websockets:
        await ws_manager.disconnect(conn["connection_id"])

@pytest.mark.asyncio
async def test_websocket_thread_interactions(
    mock_websocket: Dict[str, Any],
    concurrent_websockets: List[Dict[str, Any]],
    access_token: str,
    client: AsyncClient
) -> None:
    """Test thread interaction events:
    1. Thread reply events:
       - message.created with parent_id
       - thread.update with reply counts and latest reply
    2. Thread reaction events:
       - reaction.added to parent and replies
       - reaction.removed from parent and replies
    3. Thread message updates:
       - message.updated for replies
       - thread.update metadata after edits
    4. Thread member interactions:
       - Multiple members replying
       - Multiple members reacting
    """
    ws = mock_websocket["websocket"]
    connection_id: str = mock_websocket["connection_id"]
    user_id = mock_websocket["user_id"]
    
    # Create additional users for concurrent websockets
    debug_log("WS_THREAD_INT", "Creating additional users for concurrent websockets")
    concurrent_users = []
    for i in range(len(concurrent_websockets)):
        user_data = await register_test_user(
            client,
            email=f"test{i+2}@example.com",
            password="Password1234!",
            display_name=f"Test User {'ABCDEFGHIJK'[i]}"
        )
        concurrent_users.append(user_data)
        concurrent_websockets[i]["user_id"] = user_data["user_id"]
        concurrent_websockets[i]["token"] = user_data["access_token"]
        debug_log("WS_THREAD_INT", f"Created user {user_data['user_id']} for concurrent websocket {i+1}")
    
    # Setup test channel and add members
    debug_log("WS_THREAD_INT", "Creating test channel")
    response = await client.post(
        "/api/channels",
        json={"name": "test-thread-interactions", "type": "public"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    channel_id = response.json()["channel_id"]
    
    # Add concurrent users to channel
    for user in concurrent_users:
        response = await client.post(
            f"/api/members/{channel_id}",
            json={"user_id": user["user_id"]},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
    
    # Create parent message
    debug_log("WS_THREAD_INT", "Creating parent message")
    response = await client.post(
        "/api/messages",
        json={"content": "Parent for interactions", "channel_id": channel_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    parent_id = response.json()["message_id"]
    
    # Clear previous events
    ws.events.clear()
    for conn in concurrent_websockets:
        conn["websocket"].events.clear()
    
    # 1. Test thread reply events
    debug_log("WS_THREAD_INT", "Testing thread reply events")
    reply_ids = []
    
    # Add replies from different users
    for i, conn in enumerate(concurrent_websockets):
        response = await client.post(
            "/api/messages",
            json={
                "content": f"Reply from user {conn['user_id']}",
                "channel_id": channel_id,
                "parent_id": parent_id
            },
            headers={"Authorization": f"Bearer {conn['token']}"}
        )
        assert response.status_code == 201
        reply_ids.append(response.json()["message_id"])
        
        # Verify message.created and thread.update events
        for receiver in [ws, *[c["websocket"] for c in concurrent_websockets]]:
            # Check message.created
            messages = receiver.get_events_by_type("message.created")
            assert len(messages) > 0
            latest_message = messages[-1]
            assert latest_message["data"]["content"] == f"Reply from user {conn['user_id']}"
            assert latest_message["data"]["user_id"] == conn["user_id"]
            
        debug_log("WS_THREAD_INT", f"Reply {i+1} events verified")
    
    # 2. Test thread reaction events
    debug_log("WS_THREAD_INT", "Testing thread reaction events")
    
    # Clear previous events
    ws.events.clear()
    for conn in concurrent_websockets:
        conn["websocket"].events.clear()
    
    # Test reactions on parent message
    debug_log("WS_THREAD_INT", "Testing reactions on parent message")
    response = await client.post(
        f"/api/reactions/messages/{parent_id}",
        json={"emoji": "👍"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    
    # Verify reaction.added for parent
    for receiver in [ws, *[c["websocket"] for c in concurrent_websockets]]:
        reactions = receiver.get_events_by_type("reaction.added")
        assert len(reactions) == 1
        assert reactions[0]["data"]["message_id"] == parent_id
        assert reactions[0]["data"]["emoji"] == "👍"
        assert reactions[0]["data"]["user_id"] == user_id
        assert reactions[0]["data"]["channel_id"] == channel_id
    
    # Test reactions on replies
    debug_log("WS_THREAD_INT", "Testing reactions on replies")
    for i, reply_id in enumerate(reply_ids):
        conn = concurrent_websockets[i]
        response = await client.post(
            f"/api/reactions/messages/{reply_id}",
            json={"emoji": "❤️"},
            headers={"Authorization": f"Bearer {conn['token']}"}
        )
        assert response.status_code == 201
        
        # Verify reaction.added for reply
        for receiver in [ws, *[c["websocket"] for c in concurrent_websockets]]:
            reactions = receiver.get_events_by_type("reaction.added")
            latest_reaction = reactions[-1]
            assert latest_reaction["data"]["message_id"] == reply_id
            assert latest_reaction["data"]["emoji"] == "❤️"
            assert latest_reaction["data"]["user_id"] == conn["user_id"]
            assert latest_reaction["data"]["channel_id"] == channel_id
    
    # Test reaction removal
    debug_log("WS_THREAD_INT", "Testing reaction removal")
    
    # Remove parent reaction
    response = await client.delete(
        f"/api/reactions/messages/{parent_id}?emoji=👍",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 204
    
    # Verify reaction.removed for parent
    for receiver in [ws, *[c["websocket"] for c in concurrent_websockets]]:
        removals = receiver.get_events_by_type("reaction.removed")
        assert len(removals) > 0
        latest_removal = removals[-1]
        assert latest_removal["data"]["message_id"] == parent_id
        assert latest_removal["data"]["user_id"] == user_id
        assert latest_removal["data"]["emoji"] == "👍"
    
    # 3. Test thread message updates
    debug_log("WS_THREAD_INT", "Testing thread message updates")
    
    # Clear previous events
    ws.events.clear()
    for conn in concurrent_websockets:
        conn["websocket"].events.clear()
    
    # Update replies
    for i, reply_id in enumerate(reply_ids):
        conn = concurrent_websockets[i]
        response = await client.put(
            f"/api/messages/{reply_id}",
            json={"content": f"Updated reply from user {conn['user_id']}"},
            headers={"Authorization": f"Bearer {conn['token']}"}
        )
        assert response.status_code == 200
        
        # Verify message.updated event
        for receiver in [ws, *[c["websocket"] for c in concurrent_websockets]]:
            # Check message.updated
            updates = receiver.get_events_by_type("message.updated")
            assert len(updates) > 0
            latest_update = updates[-1]
            assert latest_update["data"]["message_id"] == reply_id
            assert latest_update["data"]["content"] == f"Updated reply from user {conn['user_id']}"
            assert latest_update["data"]["parent_id"] == parent_id
            assert latest_update["data"]["channel_id"] == channel_id
        debug_log("WS_THREAD_INT", f"Reply {i+1} update events verified")
    
    # Cleanup
    await ws_manager.disconnect(connection_id)
    for conn in concurrent_websockets:
        await ws_manager.disconnect(conn["connection_id"])

@pytest.mark.asyncio
async def test_websocket_message_visibility(
    mock_websocket: Dict[str, Any],
    concurrent_websockets: List[Dict[str, Any]],
    access_token: str,
    client: AsyncClient
) -> None:
    """Test message event delivery to channel members:
    1. Events are delivered to all channel members
    2. Events are delivered for all channel types (public, private, DM, notes)
    3. Events are delivered for all message operations (create, update, delete)
    """
    ws = mock_websocket["websocket"]
    connection_id: str = mock_websocket["connection_id"]
    user_id = mock_websocket["user_id"]
    
    # Create additional users for concurrent websockets
    debug_log("WS_MSG", "Creating additional users for concurrent websockets")
    concurrent_users = []
    for i in range(len(concurrent_websockets)):
        user_data = await register_test_user(
            client,
            email=f"test{i+2}@example.com",
            password="Password1234!",
            display_name=f"Test User {'ABCDEFGHIJK'[i]}"
        )
        concurrent_users.append(user_data)
        concurrent_websockets[i]["user_id"] = user_data["user_id"]
        concurrent_websockets[i]["token"] = user_data["access_token"]
        debug_log("WS_MSG", f"Created user {user_data['user_id']} for concurrent websocket {i+1}")
    
    # Test each channel type
    channel_types = {
        "public": {"name": "test-public", "type": "public"},
        "private": {"name": "test-private", "type": "private"},
        "notes": {"type": "notes"},  # Notes channels cannot have a name
        "dm": None  # Will be created through the DM endpoint
    }
    
    for channel_type, channel_config in channel_types.items():
        debug_log("WS_MSG", f"Testing {channel_type} channel")
        
        # Create channel
        if channel_type == "dm":
            # Create DM channel by sending a message
            response = await client.post(
                "/api/messages",
                json={
                    "content": "Test DM",
                    "recipient_id": concurrent_users[0]["user_id"]
                },
                headers={"Authorization": f"Bearer {access_token}"}
            )
            assert response.status_code == 201
            channel_id = response.json()["channel_id"]  # Message response includes channel_id
        elif channel_type == "notes":
            # Get existing notes channel (created during registration)
            response = await client.get(
                "/api/channels",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            assert response.status_code == 200
            notes_channels = [c for c in response.json() if c["type"] == "notes"]
            assert len(notes_channels) == 1, "User should have exactly one notes channel"
            response.status_code = 201  # Simulate creation response for test flow
            response._content = json.dumps(notes_channels[0]).encode()  # Encode as JSON bytes
        else:
            response = await client.post(
                "/api/channels",
                json=channel_config,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if response.status_code != 201:
                debug_log("WS_MSG", f"Channel creation failed with status {response.status_code}")
                debug_log("WS_MSG", f"Response content: {response.text}")
            assert response.status_code == 201
        channel_id = response.json()["channel_id"]
        
        # Add members for non-DM channels
        if channel_type not in ["dm", "notes"]:
            for user in concurrent_users:
                response = await client.post(
                    f"/api/members/{channel_id}",
                    json={"user_id": user["user_id"]},
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                assert response.status_code == 201
        
        # Clear previous events
        ws.events.clear()
        for conn in concurrent_websockets:
            conn["websocket"].events.clear()
        
        # Test message.created
        debug_log("WS_MSG", f"Testing message.created in {channel_type} channel")
        response = await client.post(
            "/api/messages",
            json={"content": f"Test {channel_type}", "channel_id": channel_id},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
        message_id = response.json()["message_id"]
        
        # Verify event delivery
        expected_receivers = []
        if channel_type == "dm":
            expected_receivers = [concurrent_websockets[0]]  # Only the DM recipient
        elif channel_type == "notes":
            expected_receivers = []  # Only the creator receives
        else:
            expected_receivers = concurrent_websockets  # All members for public/private
        
        for receiver in expected_receivers:
            created_events = receiver["websocket"].get_events_by_type("message.created")
            assert len(created_events) == 1
            assert created_events[0]["data"]["message_id"] == message_id
            assert created_events[0]["data"]["channel_id"] == channel_id
        
        # Test message.updated
        debug_log("WS_MSG", f"Testing message.updated in {channel_type} channel")
        response = await client.put(
            f"/api/messages/{message_id}",
            json={"content": f"Updated {channel_type}"},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 200
        
        for receiver in expected_receivers:
            updated_events = receiver["websocket"].get_events_by_type("message.updated")
            assert len(updated_events) == 1
            assert updated_events[0]["data"]["message_id"] == message_id
            assert updated_events[0]["data"]["channel_id"] == channel_id
        
        # Test message.deleted
        debug_log("WS_MSG", f"Testing message.deleted in {channel_type} channel")
        response = await client.delete(
            f"/api/messages/{message_id}",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 204
        
        for receiver in expected_receivers:
            deleted_events = receiver["websocket"].get_events_by_type("message.deleted")
            assert len(deleted_events) == 1
            assert deleted_events[0]["data"]["message_id"] == message_id
            assert deleted_events[0]["data"]["channel_id"] == channel_id
    
    # Cleanup
    await ws_manager.disconnect(connection_id)
    for conn in concurrent_websockets:
        await ws_manager.disconnect(conn["connection_id"])