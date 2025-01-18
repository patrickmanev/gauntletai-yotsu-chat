import os

# Set required environment variables before importing anything else
os.environ["YOTSU_ENVIRONMENT"] = "test"
os.environ["YOTSU_JWT_ACCESS_TOKEN_SECRET_KEY"] = "test-access-secret"
os.environ["YOTSU_JWT_REFRESH_TOKEN_SECRET_KEY"] = "test-refresh-secret"
os.environ["YOTSU_JWT_TEMP_TOKEN_SECRET_KEY"] = "test-temp-secret"

# Now we can safely import everything else
import aiosqlite
import asyncio
from typing import AsyncGenerator, Dict, Any, Union, List
import pytest
import pytest_asyncio
from httpx import AsyncClient
from fastapi.testclient import TestClient
import pyotp
import jwt
import json

from yotsu_chat.main import app
from yotsu_chat.core.database import init_db
from yotsu_chat.core.config import get_settings

# Get settings instance (will be in test mode due to environment variable)
settings = get_settings()

pytest_plugins = ["pytest_asyncio"]

class MockWebSocket:
    """Mock WebSocket class for testing WebSocket functionality"""
    def __init__(self):
        self.sent_messages: List[str] = []
        self.closed = False
        self.close_code = None
        self.close_reason = None
        self.query_params = {}
        self.accepted = False
        
    @property
    def events(self) -> List[str]:
        """Alias for sent_messages to maintain compatibility with tests"""
        return self.sent_messages
        
    async def send_text(self, message: str):
        print(f"MockWebSocket received message: {message}")  # Debug logging
        self.sent_messages.append(message)
    
    async def send_json(self, data: Any, mode: str = "text") -> None:
        if mode not in {"text", "binary"}:
            raise RuntimeError('The "mode" argument should be "text" or "binary".')
        text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        await self.send_text(text)  # Always use send_text since we store as strings
    
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
        
    def get_events_by_type(self, event_type: str) -> List[Dict[str, Any]]:
        """Helper method to get all events of a specific type"""
        return [
            json.loads(msg) for msg in self.sent_messages
            if json.loads(msg)["type"] == event_type
        ]

@pytest.fixture(autouse=True)
def setup_test_environment():
    """Setup test environment variables."""
    # Store original environment
    original_env = os.environ.copy()
    yield
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)

import pytest
from typing import AsyncGenerator, Dict, Any
from httpx import AsyncClient
from yotsu_chat.main import app
from yotsu_chat.core.config import get_settings, Settings, EnvironmentMode

@pytest.fixture(scope="function")
def event_loop():
    """Create an instance of the default event loop for each test."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    # Clean up any pending tasks
    pending = asyncio.all_tasks(loop)
    for task in pending:
        task.cancel()
    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()

async def cleanup_database():
    """Helper to clean up the database"""
    test_db_path = settings.db.get_db_path(settings.environment)
    test_db_dir = test_db_path.parent
    
    # Ensure the directory exists
    test_db_dir.mkdir(parents=True, exist_ok=True)
    
    # Clean up any existing database
    if test_db_path.exists():
        for _ in range(3):  # Try up to 3 times
            try:
                # Close any open connections and delete the file
                db = await aiosqlite.connect(str(test_db_path))
                await db.close()
                await asyncio.sleep(0.1)  # Give the OS time to release the file
                test_db_path.unlink()
                break
            except Exception as e:
                print(f"Failed to cleanup database: {e}")
                await asyncio.sleep(0.1)  # Wait a bit before retrying

@pytest_asyncio.fixture(scope="function")
async def initialized_app(event_loop):
    """Initialize the app with database setup"""
    # Clean up any existing database
    await cleanup_database()
    
    # Initialize the database
    await init_db(force=True)
    
    yield app
    
    # Clean up after the test
    await cleanup_database()

@pytest.fixture(scope="function")
def test_client(initialized_app):
    """Create a test client for the app"""
    with TestClient(initialized_app) as client:
        yield client

@pytest_asyncio.fixture(scope="function")
async def client(initialized_app) -> AsyncGenerator[AsyncClient, None]:
    """Create an async client for testing"""
    async with AsyncClient(
        app=initialized_app,
        base_url="http://test",
        timeout=5.0  # Add a reasonable timeout
    ) as client:
        yield client

async def create_test_user(client: Union[TestClient, AsyncClient], email: str, password: str, display_name: str) -> int:
    """Helper function to create a test user and return their ID"""
    if isinstance(client, AsyncClient):
        response = await client.post("/api/auth/register", json={
            "email": email,
            "password": password,
            "display_name": display_name
        })
    else:
        response = client.post("/api/auth/register", json={
            "email": email,
            "password": password,
            "display_name": display_name
        })
    assert response.status_code == 201
    temp_token = response.json()["temp_token"]
    totp_uri = response.json()["totp_uri"]
    totp_secret = pyotp.parse_uri(totp_uri).secret
    
    # Complete registration with 2FA
    totp = pyotp.TOTP(totp_secret)
    if isinstance(client, AsyncClient):
        verify_response = await client.post(
            "/api/auth/verify-2fa",
            json={"totp_code": totp.now()},
            headers={"Authorization": f"Bearer {temp_token}"}
        )
    else:
        verify_response = client.post(
            "/api/auth/verify-2fa",
            json={"totp_code": totp.now()},
            headers={"Authorization": f"Bearer {temp_token}"}
        )
    assert verify_response.status_code == 200
    tokens = verify_response.json()
    
    # Extract user_id from access token
    payload = jwt.decode(
        tokens["access_token"], 
        settings.jwt.access_token_secret_key, 
        algorithms=[settings.jwt.token_algorithm]
    )
    return payload["user_id"]

async def register_test_user(
    client: AsyncClient,
    email: str,
    password: str,
    display_name: str
) -> Dict[str, Any]:
    """Register a test user and complete the authentication flow"""
    # 1. Register user
    response = await client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "display_name": display_name
    })
    assert response.status_code == 201, f"Registration failed: {response.text}"
    temp_token = response.json()["temp_token"]
    totp_uri = response.json()["totp_uri"]
    totp_secret = pyotp.parse_uri(totp_uri).secret
    
    # Complete registration with 2FA
    totp = pyotp.TOTP(totp_secret)
    verify_response = await client.post(
        "/api/auth/verify-2fa",
        json={"totp_code": totp.now()},
        headers={"Authorization": f"Bearer {temp_token}"}
    )
    assert verify_response.status_code == 200, f"2FA verification failed: {verify_response.text}"
    tokens = verify_response.json()
    
    # Extract user_id from access token
    payload = jwt.decode(
        tokens["access_token"], 
        settings.jwt.access_token_secret_key, 
        algorithms=[settings.jwt.token_algorithm]
    )
    
    return {
        "user_id": payload["user_id"],
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"]
    }

@pytest_asyncio.fixture
async def access_token(client: AsyncClient) -> str:
    """Create a test user and return their access token"""
    user_id = await create_test_user(
        client,
        email="test@example.com",
        password="Password1234!",
        display_name="John Smith"
    )
    
    response = await client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "Password1234!"
    })
    assert response.status_code == 200
    data = response.json()
    return data["access_token"]

@pytest_asyncio.fixture
async def second_user_token(client: AsyncClient) -> Dict[str, Any]:
    """Create a second test user and return their access token and user_id"""
    user_id = await create_test_user(
        client,
        email="test2@example.com",
        password="Password1234!",
        display_name="Jane Smith"
    )
    
    response = await client.post("/api/auth/login", json={
        "email": "test2@example.com",
        "password": "Password1234!"
    })
    assert response.status_code == 200
    data = response.json()
    return {
        "access_token": data["access_token"],
        "user_id": user_id
    }

@pytest_asyncio.fixture
async def test_channel(client: AsyncClient, access_token: str) -> Dict[str, Any]:
    """Create a test channel and return its data"""
    response = await client.post(
        "/api/channels",
        json={"name": "test-channel", "type": "public"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    return response.json()

@pytest_asyncio.fixture
async def thread_with_reply(client: AsyncClient, access_token: str, test_channel: Dict[str, Any]) -> Dict[str, Any]:
    """Create a thread with a parent message and one reply"""
    channel_id = test_channel["channel_id"]
    
    # Create parent message
    parent_response = await client.post(
        f"/api/messages/channels/{channel_id}",
        json={"content": "Parent message"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert parent_response.status_code == 201
    parent_data = parent_response.json()
    
    # Create reply
    reply_response = await client.post(
        f"/api/messages/channels/{channel_id}",
        json={
            "content": "Reply message",
            "parent_id": parent_data["message_id"]
        },
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert reply_response.status_code == 201
    reply_data = reply_response.json()
    
    return {
        "parent": parent_data,
        "reply": reply_data
    }

@pytest_asyncio.fixture
async def test_message(client: AsyncClient, access_token: str, test_channel: Dict[str, Any]) -> Dict[str, Any]:
    """Create a test message and return its data"""
    channel_id = test_channel["channel_id"]
    
    response = await client.post(
        "/api/messages",
        json={"content": "Test message for reactions", "channel_id": channel_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    return response.json() 

import pytest
from httpx import AsyncClient
from typing import Dict, Any, List, AsyncGenerator
import asyncio
from datetime import datetime, timedelta, UTC
from yotsu_chat.core.ws_core import manager as ws_manager
import uuid

@pytest.fixture
async def expired_token(client: AsyncClient) -> str:
    """Create a token that is already expired"""
    response = await client.post(
        "/api/auth/login",
        json={
            "email": "test@example.com",
            "password": "Password1234!",
            "totp_code": "123456"
        }
    )
    assert response.status_code == 200
    token_data = response.json()
    
    # Manually create an expired token with same user_id but past expiration
    from yotsu_chat.services.token_service import token_service
    expired = token_service.create_access_token(
        {"user_id": 1},  # First test user
        expires_delta=timedelta(minutes=-5)  # Expired 5 minutes ago
    )
    return expired

@pytest_asyncio.fixture
async def rate_limited_websocket(access_token: str) -> AsyncGenerator[Dict[str, Any], None]:
    """Create a WebSocket connection with rate limiting metadata"""
    ws = MockWebSocket()
    ws.query_params["token"] = access_token
    connection_id = str(uuid.uuid4())
    
    # Connect and authenticate
    user_id = await ws_manager.authenticate_connection(ws)
    await ws_manager.connect(ws, user_id, connection_id)
    
    # Add rate limiting metadata
    ws_manager.connection_rate_limits[connection_id] = {
        "message_count": 0,
        "last_reset": datetime.now(UTC),
        "rate_limit": 10,  # messages per minute
        "time_window": 60  # seconds
    }
    
    connection = {
        "websocket": ws,
        "connection_id": connection_id,
        "user_id": user_id
    }
    
    yield connection
    
    # Cleanup
    await ws_manager.disconnect(connection_id)
    if connection_id in ws_manager.connection_rate_limits:
        del ws_manager.connection_rate_limits[connection_id]

@pytest_asyncio.fixture
async def mock_websocket(access_token: str) -> AsyncGenerator[Dict[str, Any], None]:
    """Create a mock WebSocket connection for testing"""
    ws = MockWebSocket()
    ws.query_params["token"] = access_token
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

@pytest_asyncio.fixture
async def concurrent_websockets(client: AsyncClient) -> AsyncGenerator[List[Dict[str, Any]], None]:
    """Create multiple WebSocket connections for concurrent testing"""
    connections = []
    for i in range(3):  # Create 3 concurrent connections
        # Create a unique user for each connection
        user_data = await register_test_user(
            client,
            email=f"concurrent{i+1}@example.com",
            password="Password1234!",
            display_name=f"User {chr(65 + i)}"  # A, B, C
        )
        
        ws = MockWebSocket()
        ws.query_params["token"] = user_data["access_token"]
        connection_id = str(uuid.uuid4())
        
        # Connect and authenticate
        user_id = await ws_manager.authenticate_connection(ws)
        await ws_manager.connect(ws, user_id, connection_id)  # This triggers auto-subscription
        
        connections.append({
            "websocket": ws,
            "connection_id": connection_id,
            "user_id": user_id,
            "token": user_data["access_token"]  # Store the token for later use
        })
    
    yield connections
    
    # Cleanup
    for conn in connections:
        await ws_manager.disconnect(conn["connection_id"]) 

@pytest_asyncio.fixture(autouse=True)
async def cleanup_manager() -> None:
    """Cleanup the WebSocket manager after each test"""
    yield
    await ws_manager.cleanup()
    ws_manager._health_check_task = None
    ws_manager.active_connections.clear()
    ws_manager.subscription_groups.clear()
    ws_manager.connection_health.clear()
    ws_manager.connection_rate_limits.clear() 