import pytest
import pytest_asyncio
from typing import Dict, Any, List
import uuid
import json
from yotsu_chat.core.ws_core import manager as ws_manager, WebSocketError
from tests.conftest import MockWebSocket, register_test_user
import asyncio
from datetime import datetime, timedelta, UTC

# Helper function to get presence events from a websocket
def get_presence_events(websocket) -> List[Dict[str, Any]]:
    """Extract presence-related events from websocket messages"""
    presence_events = []
    for msg in websocket.sent_messages:
        try:
            data = json.loads(msg)
            if data["type"] in ["presence.initial", "presence.update"]:
                presence_events.append(data)
        except (json.JSONDecodeError, KeyError):
            continue
    return presence_events

@pytest_asyncio.fixture
async def second_mock_websocket(second_user_token: Dict[str, Any]) -> Dict[str, Any]:
    """Create a mock WebSocket connection for the second test user"""
    ws = MockWebSocket()
    ws.query_params["token"] = second_user_token["access_token"]
    connection_id = str(uuid.uuid4())
    
    # Connect and authenticate
    user_id = await ws_manager.authenticate_connection(ws)
    await ws_manager.connect(ws, user_id, connection_id)
    
    connection = {
        "websocket": ws,
        "connection_id": connection_id,
        "user_id": user_id
    }
    
    yield connection
    
    # Cleanup
    await ws_manager.disconnect(connection_id)

# Basic Presence Tests
@pytest.mark.asyncio
async def test_first_connection_marks_user_online(mock_websocket):
    """Test that first connection marks user as online"""
    user_id = mock_websocket["user_id"]
    assert user_id in ws_manager.online_users
    assert ws_manager.user_connection_count[user_id] == 1

@pytest.mark.asyncio
async def test_last_disconnect_marks_user_offline(mock_websocket):
    """Test that last disconnection marks user as offline"""
    user_id = mock_websocket["user_id"]
    connection_id = mock_websocket["connection_id"]
    
    # Verify initial state
    assert user_id in ws_manager.online_users
    
    # Disconnect
    await ws_manager.disconnect(connection_id)
    
    # Verify offline state
    assert user_id not in ws_manager.online_users
    assert user_id not in ws_manager.user_connection_count

@pytest.mark.asyncio
async def test_multiple_connections_same_user(mock_websocket):
    """Test multiple connections from same user"""
    user_id = mock_websocket["user_id"]
    ws = MockWebSocket()
    ws.query_params["token"] = mock_websocket["websocket"].query_params["token"]
    second_connection_id = str(uuid.uuid4())
    
    # Create second connection
    await ws_manager.authenticate_connection(ws)
    await ws_manager.connect(ws, user_id, second_connection_id)
    
    try:
        # Verify user is still online with 2 connections
        assert user_id in ws_manager.online_users
        assert ws_manager.user_connection_count[user_id] == 2
        
        # Disconnect first connection
        await ws_manager.disconnect(mock_websocket["connection_id"])
        
        # Verify user is still online
        assert user_id in ws_manager.online_users
        assert ws_manager.user_connection_count[user_id] == 1
        
        # Disconnect second connection
        await ws_manager.disconnect(second_connection_id)
        
        # Verify user is now offline
        assert user_id not in ws_manager.online_users
        assert user_id not in ws_manager.user_connection_count
    finally:
        # Cleanup
        await ws_manager.disconnect(second_connection_id)

# Connection Edge Cases
@pytest.mark.asyncio
async def test_failed_connection_invalid_token():
    """Test connection attempt with invalid token"""
    ws = MockWebSocket()
    ws.query_params["token"] = "invalid_token"
    
    with pytest.raises(WebSocketError) as exc_info:
        await ws_manager.authenticate_connection(ws)
    assert exc_info.value.code == 1008
    assert "Invalid authentication token" in str(exc_info.value)

@pytest.mark.asyncio
async def test_connection_cleanup_on_server_shutdown(mock_websocket):
    """Test proper cleanup of connections on server shutdown"""
    user_id = mock_websocket["user_id"]
    
    # Verify initial state
    assert user_id in ws_manager.online_users
    
    # Simulate server shutdown
    await ws_manager.cleanup()
    
    # Verify all state is cleaned up
    assert len(ws_manager.active_connections) == 0
    assert len(ws_manager.online_users) == 0
    assert len(ws_manager.user_connection_count) == 0

# Multi-Connection Scenarios
@pytest.mark.asyncio
async def test_partial_disconnect_keeps_user_online(concurrent_websockets):
    """Test that user stays online when only some connections are closed"""
    user_id = concurrent_websockets[0]["user_id"]
    
    # Verify initial state
    assert user_id in ws_manager.online_users
    assert ws_manager.user_connection_count[user_id] == 3
    
    # Disconnect one connection
    await ws_manager.disconnect(concurrent_websockets[0]["connection_id"])
    
    # Verify user is still online with fewer connections
    assert user_id in ws_manager.online_users
    assert ws_manager.user_connection_count[user_id] == 2

# Initial Presence List Tests
@pytest.mark.asyncio
async def test_new_connection_receives_online_users(mock_websocket, second_mock_websocket):
    """Test that new connections receive the current list of online users"""
    # Get presence events from second connection
    presence_events = get_presence_events(second_mock_websocket["websocket"])
    initial_presence = next(
        (e for e in presence_events if e["type"] == "presence.initial"),
        None
    )
    
    # Verify initial presence data
    assert initial_presence is not None
    assert "online_users" in initial_presence["data"]
    assert mock_websocket["user_id"] in initial_presence["data"]["online_users"]
    assert second_mock_websocket["user_id"] in initial_presence["data"]["online_users"]

@pytest.mark.asyncio
async def test_empty_online_users_list(mock_websocket):
    """Test initial presence list when no other users are online"""
    # Disconnect the only user
    await ws_manager.disconnect(mock_websocket["connection_id"])
    
    # Create new connection
    ws = MockWebSocket()
    ws.query_params["token"] = mock_websocket["websocket"].query_params["token"]
    new_connection_id = str(uuid.uuid4())
    
    try:
        # Connect new user
        user_id = await ws_manager.authenticate_connection(ws)
        await ws_manager.connect(ws, user_id, new_connection_id)
        
        # Get presence events
        presence_events = get_presence_events(ws)
        initial_presence = next(
            (e for e in presence_events if e["type"] == "presence.initial"),
            None
        )
        
        # Verify initial presence data
        assert initial_presence is not None
        assert len(initial_presence["data"]["online_users"]) == 1
        assert user_id in initial_presence["data"]["online_users"]
    finally:
        await ws_manager.disconnect(new_connection_id)

# Broadcast Behavior Tests
@pytest.mark.asyncio
async def test_presence_broadcast_on_connect(mock_websocket, second_mock_websocket):
    """Test that presence changes are broadcast when users connect"""
    # Get presence events from first connection
    presence_events = get_presence_events(mock_websocket["websocket"])
    presence_updates = [
        e for e in presence_events 
        if e["type"] == "presence.update" and 
        e["data"]["user_id"] == second_mock_websocket["user_id"]
    ]
    
    # Verify presence update was broadcast
    assert len(presence_updates) > 0
    assert presence_updates[-1]["data"]["status"] == "online"

@pytest.mark.asyncio
async def test_presence_broadcast_on_disconnect(mock_websocket, second_mock_websocket):
    """Test that presence changes are broadcast when users disconnect"""
    # Disconnect second user
    await ws_manager.disconnect(second_mock_websocket["connection_id"])
    
    # Get presence events from first connection
    presence_events = get_presence_events(mock_websocket["websocket"])
    presence_updates = [
        e for e in presence_events 
        if e["type"] == "presence.update" and 
        e["data"]["user_id"] == second_mock_websocket["user_id"]
    ]
    
    # Verify presence update was broadcast
    assert len(presence_updates) > 0
    assert presence_updates[-1]["data"]["status"] == "offline"

@pytest.mark.asyncio
async def test_no_duplicate_broadcasts_same_user(mock_websocket):
    """Test that multiple connections from same user don't cause duplicate broadcasts"""
    user_id = mock_websocket["user_id"]
    ws = MockWebSocket()
    ws.query_params["token"] = mock_websocket["websocket"].query_params["token"]
    second_connection_id = str(uuid.uuid4())
    
    try:
        # Create second connection
        await ws_manager.authenticate_connection(ws)
        await ws_manager.connect(ws, user_id, second_connection_id)
        
        # Get presence events from first connection
        presence_events = get_presence_events(mock_websocket["websocket"])
        presence_updates = [
            e for e in presence_events 
            if e["type"] == "presence.update" and 
            e["data"]["user_id"] == user_id
        ]
        
        # Verify no duplicate online broadcasts
        online_updates = [
            u for u in presence_updates 
            if u["data"]["status"] == "online"
        ]
        assert len(online_updates) == 1
    finally:
        await ws_manager.disconnect(second_connection_id) 

# Advanced Presence Test Scenarios
@pytest.mark.asyncio
async def test_concurrent_presence_updates(client):
    """Test concurrent connections/disconnections don't corrupt presence state"""
    # Create multiple connections simultaneously
    connections = []
    user_tokens = []
    test_users = [
        ("alpha@test.com", "Alpha User"),
        ("beta@test.com", "Beta User"),
        ("gamma@test.com", "Gamma User"),
        ("delta@test.com", "Delta User"),
        ("epsilon@test.com", "Epsilon User")
    ]
    
    for email, name in test_users:
        token = await register_test_user(client, email, "Password123!", name)
        user_tokens.append(token)
    
    # Simulate concurrent connections
    async def connect_and_disconnect(token):
        ws = MockWebSocket()
        ws.query_params["token"] = token["access_token"]
        conn_id = str(uuid.uuid4())
        user_id = await ws_manager.authenticate_connection(ws)
        await ws_manager.connect(ws, user_id, conn_id)
        return {"ws": ws, "conn_id": conn_id, "user_id": user_id}
    
    # Connect all users concurrently
    tasks = [connect_and_disconnect(token) for token in user_tokens]
    connections = await asyncio.gather(*tasks)
    
    try:
        # Verify all users are online
        assert len(ws_manager.online_users) == 5
        
        # Disconnect half the users concurrently
        disconnect_tasks = [
            ws_manager.disconnect(conn["conn_id"]) 
            for conn in connections[:3]
        ]
        await asyncio.gather(*disconnect_tasks)
        
        # Verify correct number of users remain online
        assert len(ws_manager.online_users) == 2
    finally:
        # Cleanup
        for conn in connections[3:]:
            await ws_manager.disconnect(conn["conn_id"])

@pytest.mark.asyncio
async def test_connection_failure_handling(mock_websocket):
    """Test handling of network failures during presence updates"""
    user_id = mock_websocket["user_id"]
    ws = mock_websocket["websocket"]
    
    # Simulate network failure during send
    async def mock_send_failure(*args, **kwargs):
        raise ConnectionError("Network failure")
    
    # Replace send_json with failing version
    original_send = ws.send_json
    ws.send_json = mock_send_failure
    
    try:
        # Attempt to send presence update
        await ws_manager._broadcast_presence_change(user_id, True)
        
        # Verify user's presence state remains consistent
        assert user_id in ws_manager.online_users
    finally:
        # Restore original send function
        ws.send_json = original_send

@pytest.mark.asyncio
async def test_health_check_presence_sync(client):
    """Test that health checks properly maintain presence state"""
    # Register a test user
    token = await register_test_user(
        client,
        "health@test.com",
        "Password123!",
        "Health Test User"
    )
    
    ws = MockWebSocket()
    ws.query_params["token"] = token["access_token"]
    connection_id = str(uuid.uuid4())
    
    # Connect user
    user_id = await ws_manager.authenticate_connection(ws)
    await ws_manager.connect(ws, user_id, connection_id)
    
    try:
        # Simulate failed health checks
        ws_manager.connection_health[connection_id]["last_pong"] = (
            datetime.now(UTC) - timedelta(seconds=100)
        )
        
        # Call the internal health check logic directly
        dead_connections = set()
        now = datetime.now(UTC)
        
        # Replicate the core health check logic without the loop
        for conn_id, health in ws_manager.connection_health.items():
            if now - health["last_pong"] > timedelta(seconds=90):
                dead_connections.add(conn_id)
        
        # Process dead connections
        for conn_id in dead_connections:
            await ws_manager.disconnect(conn_id)
        
        # Verify user is marked offline after health check failure
        assert user_id not in ws_manager.online_users
        assert user_id not in ws_manager.user_connection_count
    
    finally:
        # Cleanup
        await ws_manager.disconnect(connection_id)

@pytest.mark.asyncio
async def test_presence_state_recovery(client):
    """Test presence state recovery after connection manager restart"""
    # Store initial state
    initial_connections = []
    test_users = [
        ("recovery_a@test.com", "Recovery Alpha"),
        ("recovery_b@test.com", "Recovery Beta"),
        ("recovery_c@test.com", "Recovery Charlie")
    ]
    
    for email, name in test_users:
        ws = MockWebSocket()
        token = await register_test_user(client, email, "Password123!", name)
        ws.query_params["token"] = token["access_token"]
        conn_id = str(uuid.uuid4())
        user_id = await ws_manager.authenticate_connection(ws)
        await ws_manager.connect(ws, user_id, conn_id)
        initial_connections.append({
            "ws": ws,
            "conn_id": conn_id,
            "user_id": user_id
        })
    
    try:
        # Simulate manager restart
        await ws_manager.cleanup()
        
        # Reconnect all users
        for conn in initial_connections:
            await ws_manager.connect(conn["ws"], conn["user_id"], str(uuid.uuid4()))
        
        # Verify presence state is correctly restored
        assert len(ws_manager.online_users) == 3
        for conn in initial_connections:
            assert conn["user_id"] in ws_manager.online_users
    finally:
        # Cleanup
        for conn in initial_connections:
            await ws_manager.disconnect(conn["conn_id"])

@pytest.mark.asyncio
async def test_rapid_tab_switching(client):
    """Test rapid connect/disconnect cycles from same user"""
    # Register test user
    token = await register_test_user(
        client,
        "tabswitch@test.com",
        "Password123!",
        "Tab Switch User"
    )

    # Get user_id from the first connection to use for cleanup
    initial_ws = MockWebSocket()
    initial_ws.query_params["token"] = token["access_token"]
    user_id = await ws_manager.authenticate_connection(initial_ws)
    
    # Clean up any existing connections for this user
    connections_to_remove = [
        conn_id for conn_id, uid in ws_manager.connection_users.items() 
        if uid == user_id
    ]
    for conn_id in connections_to_remove:
        await ws_manager.disconnect(conn_id)
    
    # Verify clean slate
    assert user_id not in ws_manager.user_connection_count
    assert user_id not in ws_manager.online_users

    # Simulate rapid tab switching
    connection_ids = []
    websockets = []

    try:
        for i in range(10):  # Simulate opening 10 tabs rapidly
            # Create new WebSocket for each tab
            ws = MockWebSocket()
            ws.query_params["token"] = token["access_token"]
            websockets.append(ws)

            conn_id = str(uuid.uuid4())
            await ws_manager.authenticate_connection(ws)
            await ws_manager.connect(ws, user_id, conn_id)
            connection_ids.append(conn_id)

            # Immediately close previous tab and verify it's closed
            if len(connection_ids) > 1:
                prev_conn_id = connection_ids[-2]
                await ws_manager.disconnect(prev_conn_id)
                # Verify the disconnect completed
                assert prev_conn_id not in ws_manager.active_connections
                assert prev_conn_id not in ws_manager.connection_users
                assert ws_manager.user_connection_count[user_id] == 1

    finally:
        # Clean up any remaining connections
        for conn_id in connection_ids:
            if conn_id in ws_manager.active_connections:
                await ws_manager.disconnect(conn_id)
        assert user_id not in ws_manager.user_connection_count
        assert user_id not in ws_manager.online_users

@pytest.mark.asyncio
async def test_presence_after_token_expiry(client, expired_token):
    """Test presence handling when a user's token expires"""
    ws = MockWebSocket()
    ws.query_params["token"] = expired_token
    
    # Attempt connection with expired token
    with pytest.raises(WebSocketError) as exc_info:
        await ws_manager.authenticate_connection(ws)
    
    assert exc_info.value.code == 1008
    assert "Invalid authentication token" in str(exc_info.value)

@pytest.mark.asyncio
async def test_presence_sync_across_connections(mock_websocket, second_mock_websocket):
    """Test that presence state is synchronized across all connections"""
    first_user_id = mock_websocket["user_id"]
    second_user_id = second_mock_websocket["user_id"]
    
    # Clean up any existing connections for both users
    for user_id in [first_user_id, second_user_id]:
        connections_to_remove = [
            conn_id for conn_id, uid in ws_manager.connection_users.items() 
            if uid == user_id
        ]
        for conn_id in connections_to_remove:
            await ws_manager.disconnect(conn_id)
        
        # Verify clean slate
        assert user_id not in ws_manager.user_connection_count
        assert user_id not in ws_manager.online_users
    
    # Reconnect both users with clean connections
    await ws_manager.connect(mock_websocket["websocket"], first_user_id, mock_websocket["connection_id"])
    await ws_manager.connect(second_mock_websocket["websocket"], second_user_id, second_mock_websocket["connection_id"])
    
    # Both users should be online
    assert first_user_id in ws_manager.online_users
    assert second_user_id in ws_manager.online_users
    
    # Get presence events from both connections
    first_events = get_presence_events(mock_websocket["websocket"])
    second_events = get_presence_events(second_mock_websocket["websocket"])
    
    # Verify each user received the other's presence
    first_received_second = any(
        e["type"] == "presence.update" and 
        e["data"]["user_id"] == second_user_id and 
        e["data"]["status"] == "online" 
        for e in first_events
    )
    
    second_received_first = any(
        e["type"] == "presence.initial" and 
        first_user_id in e["data"]["online_users"]
        for e in second_events
    )
    
    assert first_received_second
    assert second_received_first 

@pytest.mark.asyncio
async def test_health_check_fixes_inconsistent_count(client):
    """Test that health check corrects inconsistent connection counts"""
    # Register test user
    token = await register_test_user(
        client,
        "inconsistent@test.com",
        "Password123!",
        "Inconsistent User"
    )
    
    # Create connection
    ws = MockWebSocket()
    ws.query_params["token"] = token["access_token"]
    connection_id = str(uuid.uuid4())
    user_id = await ws_manager.authenticate_connection(ws)
    await ws_manager.connect(ws, user_id, connection_id)
    
    try:
        # Artificially create inconsistent state
        ws_manager.user_connection_count[user_id] = 3  # Wrong count
        
        # Wait for health check to run (using test timing)
        await asyncio.sleep(1.1)  # Slightly longer than health check interval
        
        # Verify the count was corrected
        assert ws_manager.user_connection_count[user_id] == 1
        assert user_id in ws_manager.online_users
        
    finally:
        await ws_manager.disconnect(connection_id)

@pytest.mark.asyncio
async def test_health_check_removes_phantom_users(client):
    """Test that health check removes users marked as online with no connections"""
    # Register test user
    token = await register_test_user(
        client,
        "phantom@test.com",
        "Password123!",
        "Phantom User"
    )
    
    # Create and immediately disconnect a connection to get a user_id
    ws = MockWebSocket()
    ws.query_params["token"] = token["access_token"]
    connection_id = str(uuid.uuid4())
    user_id = await ws_manager.authenticate_connection(ws)
    await ws_manager.connect(ws, user_id, connection_id)
    await ws_manager.disconnect(connection_id)
    
    # Artificially create phantom online state
    ws_manager.online_users.add(user_id)
    ws_manager.user_connection_count[user_id] = 1
    
    # Wait for health check to run
    await asyncio.sleep(1.1)
    
    # Verify phantom user was removed
    assert user_id not in ws_manager.online_users
    assert user_id not in ws_manager.user_connection_count

@pytest.mark.asyncio
async def test_health_check_handles_multiple_inconsistencies(client):
    """Test that health check can handle multiple types of inconsistencies simultaneously"""
    # Register two test users
    tokens = []
    user_ids = []
    test_users = [
        ("multi.a@test.com", "First Test User"),
        ("multi.b@test.com", "Second Test User")
    ]
    
    for email, name in test_users:
        token = await register_test_user(
            client,
            email,
            "Password123!",
            name
        )
        tokens.append(token)
        
        # Create initial connection to get user_id
        ws = MockWebSocket()
        ws.query_params["token"] = token["access_token"]
        user_id = await ws_manager.authenticate_connection(ws)
        user_ids.append(user_id)
    
    connections = []
    try:
        # Create actual connection for first user
        ws1 = MockWebSocket()
        ws1.query_params["token"] = tokens[0]["access_token"]
        conn_id1 = str(uuid.uuid4())
        await ws_manager.authenticate_connection(ws1)
        await ws_manager.connect(ws1, user_ids[0], conn_id1)
        connections.append(conn_id1)
        
        # Create artificial inconsistencies
        ws_manager.user_connection_count[user_ids[0]] = 3  # Wrong count for connected user
        ws_manager.online_users.add(user_ids[1])  # Phantom online user
        ws_manager.user_connection_count[user_ids[1]] = 1
        
        # Wait for health check to run
        await asyncio.sleep(1.1)
        
        # Verify all inconsistencies were fixed
        assert ws_manager.user_connection_count[user_ids[0]] == 1  # Corrected count
        assert user_ids[0] in ws_manager.online_users  # Real user still online
        assert user_ids[1] not in ws_manager.online_users  # Phantom user removed
        assert user_ids[1] not in ws_manager.user_connection_count  # Phantom user count removed
        
    finally:
        for conn_id in connections:
            await ws_manager.disconnect(conn_id) 