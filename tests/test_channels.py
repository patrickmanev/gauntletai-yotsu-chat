import asyncio
import httpx
import json
import base64
import pyotp
import pytest
import os
from typing import Dict, Any
from app.main import app
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

@pytest.fixture(autouse=True)
async def setup_database():
    """Initialize the database before each test"""
    if os.path.exists("yotsu_chat.db"):
        os.remove("yotsu_chat.db")
    from app.core.database import init_db
    await init_db()
    yield
    if os.path.exists("yotsu_chat.db"):
        os.remove("yotsu_chat.db")

async def register_test_user(
    client: AsyncClient,
    email: str,
    password: str,
    display_name: str
) -> Dict[str, Any]:
    """Register a test user and complete the authentication flow"""
    # Set test mode
    os.environ["TEST_MODE"] = "true"
    
    # 1. Register user
    response = await client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "display_name": display_name
    })
    assert response.status_code == 201, f"Registration failed: {response.text}"
    user_data = response.json()
    
    # 2. Login
    response = await client.post("/api/auth/login", json={
        "email": email,
        "password": password
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    tokens = response.json()
    
    return {
        "user_id": user_data["user_id"],
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"]
    }

async def test_channel_operations(client: AsyncClient):
    """Test channel operations"""
    print("\n1. Setting up test users...")
    
    # Create test users
    user1 = await register_test_user(
        client,
        email="user1@example.com",
        password="password123",
        display_name="User One"
    )
    
    user2 = await register_test_user(
        client,
        email="user2@example.com",
        password="password123",
        display_name="User Two"
    )
    
    user3 = await register_test_user(
        client,
        email="user3@example.com",
        password="password123",
        display_name="User Three"
    )
    
    print("\n2. Testing channel creation...")
    # Create a channel
    response = await client.post(
        "/api/channels",
        json={
            "name": "Test Channel",
            "type": "public",
            "initial_members": [user2["user_id"]]
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201, f"Channel creation failed: {response.text}"
    channel_data = response.json()
    channel_id = channel_data["channel_id"]
    
    print("\n3. Testing channel listing...")
    # List channels for user1
    response = await client.get(
        "/api/channels",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200, f"Channel listing failed: {response.text}"
    channels = response.json()
    assert len(channels) == 1, "Expected one channel"
    assert channels[0]["channel_id"] == channel_id
    assert channels[0]["role"] == "owner"
    
    # List channels for user2
    response = await client.get(
        "/api/channels",
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 200, f"Channel listing failed: {response.text}"
    channels = response.json()
    assert len(channels) == 1, "Expected one channel"
    assert channels[0]["channel_id"] == channel_id
    assert channels[0]["role"] == "member"
    
    print("\n4. Testing channel member listing...")
    # List channel members
    response = await client.get(
        f"/api/channels/{channel_id}/members",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200, f"Member listing failed: {response.text}"
    members = response.json()
    assert len(members) == 2, "Expected two members"
    
    print("\n5. Testing adding new member...")
    # Add user3 to the channel
    response = await client.post(
        f"/api/channels/{channel_id}/members",
        json={
            "user_id": user3["user_id"],
            "role": "member"
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200, f"Adding member failed: {response.text}"
    new_member = response.json()
    assert new_member["user_id"] == user3["user_id"]
    assert new_member["role"] == "member"
    
    # Verify member count increased
    response = await client.get(
        f"/api/channels/{channel_id}/members",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    members = response.json()
    assert len(members) == 3, "Expected three members after adding user3"
    
    print("\n6. Testing duplicate member addition...")
    # Try to add user3 again
    response = await client.post(
        f"/api/channels/{channel_id}/members",
        json={
            "user_id": user3["user_id"],
            "role": "member"
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 400, "Expected error when adding duplicate member"
    
    print("\n7. Testing member removal...")
    # Remove user2 from the channel
    response = await client.delete(
        f"/api/channels/{channel_id}/members/{user2['user_id']}",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200, f"Removing member failed: {response.text}"
    
    # Verify member count decreased
    response = await client.get(
        f"/api/channels/{channel_id}/members",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    members = response.json()
    assert len(members) == 2, "Expected two members after removing user2"
    member_ids = [m["user_id"] for m in members]
    assert user2["user_id"] not in member_ids, "Removed user should not be in member list"

if __name__ == "__main__":
    asyncio.run(test_channel_operations()) 