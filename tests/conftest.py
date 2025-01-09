import os
# Set test mode for the entire test session
os.environ["TEST_MODE"] = "1"

import pytest
from typing import AsyncGenerator, Dict, Any, Union
import pytest_asyncio
from httpx import AsyncClient
import aiosqlite
import asyncio
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute, APIWebSocketRoute
import pyotp
import jwt

from yotsu_chat.main import app
from yotsu_chat.core.database import init_db
from yotsu_chat.core.auth import SECRET_KEY, ALGORITHM

pytest_plugins = ["pytest_asyncio"]

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
    test_db_path = "data/db/test/test_yotsu_chat.db"
    test_db_dir = os.path.dirname(test_db_path)
    
    # Ensure the directory exists
    os.makedirs(test_db_dir, exist_ok=True)
    
    # Clean up any existing database
    if os.path.exists(test_db_path):
        for _ in range(3):  # Try up to 3 times
            try:
                # Close any open connections and delete the file
                db = await aiosqlite.connect(test_db_path)
                await db.close()
                await asyncio.sleep(0.1)  # Give the OS time to release the file
                os.remove(test_db_path)
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
    payload = jwt.decode(tokens["access_token"], SECRET_KEY, algorithms=[ALGORITHM])
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
    payload = jwt.decode(tokens["access_token"], SECRET_KEY, algorithms=[ALGORITHM])
    
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
        json={"name": "Test-Channel"},
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
        f"/api/messages/channels/{channel_id}",
        json={"content": "Test message for reactions"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    return response.json() 