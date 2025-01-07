import asyncio
import httpx
import json
import base64
import pyotp
import pytest
import os
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

@pytest.fixture(autouse=True)
async def cleanup_database():
    """Clean up the database before each test"""
    if os.path.exists("yotsu_chat.db"):
        os.remove("yotsu_chat.db")
    from app.core.database import init_db
    await init_db()
    yield
    if os.path.exists("yotsu_chat.db"):
        os.remove("yotsu_chat.db")

async def test_auth_flow(client: AsyncClient):
    """Test the complete authentication flow"""
    # 1. Test registration
    print("\n1. Testing registration...")
    response = await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "password123",
        "display_name": "Test User"
    })
    print(f"Registration response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    assert response.status_code == 201, "Registration failed"
    totp_secret = response.json()["totp_secret"]
    
    # 2. Test login
    print("\n2. Testing login...")
    response = await client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "password123"
    })
    print(f"Login response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    assert response.status_code == 200, "Login failed"
    
    # Check if we're in test mode (access token returned) or normal mode (temp token returned)
    response_data = response.json()
    if "access_token" in response_data:
        # Test mode - we already have the tokens
        access_token = response_data["access_token"]
        refresh_token = response_data["refresh_token"]
        assert access_token is not None, "Access token not returned"
        assert refresh_token is not None, "Refresh token not returned"
    else:
        # Normal mode - need to do 2FA
        temp_token = response_data["temp_token"]
        assert temp_token is not None, "Temp token not returned"
        
        # 3. Test 2FA verification
        print("\n3. Testing 2FA verification...")
        totp = pyotp.TOTP(totp_secret)
        response = await client.post(
            "/api/auth/verify-2fa",
            json={"totp_code": totp.now()},
            headers={"Authorization": f"Bearer {temp_token}"}
        )
        print(f"2FA verification response: {response.status_code}")
        print(json.dumps(response.json(), indent=2))
        assert response.status_code == 200, "2FA verification failed"
        response_data = response.json()
        access_token = response_data["access_token"]
        refresh_token = response_data["refresh_token"]
        assert access_token is not None, "Access token not returned"
        assert refresh_token is not None, "Refresh token not returned"
    
    # 4. Test token refresh
    print("\n4. Testing token refresh...")
    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    print(f"Token refresh response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    assert response.status_code == 200, "Token refresh failed"
    response_data = response.json()
    assert response_data["access_token"] is not None, "New access token not returned"
    assert response_data["refresh_token"] is not None, "New refresh token not returned"

async def test_invalid_credentials(client: AsyncClient):
    """Test invalid login scenarios"""
    # Test non-existent email
    response = await client.post("/api/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "password123"
    })
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]

    # Test wrong password
    # First register a user
    await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "password123",
        "display_name": "Test User"
    })
    
    # Try login with wrong password
    response = await client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "wrongpassword"
    })
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]

async def test_token_security(client: AsyncClient):
    """Test token security and access control"""
    # Temporarily disable test mode
    original_test_mode = os.getenv("TEST_MODE")
    os.environ["TEST_MODE"] = "false"
    
    try:
        # Register and login
        register_response = await client.post("/api/auth/register", json={
            "email": "test@example.com",
            "password": "password123",
            "display_name": "Test User"
        })
        totp_secret = register_response.json()["totp_secret"]
        
        login_response = await client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "password123"
        })
        login_data = login_response.json()
        
        if "temp_token" in login_data:
            # Test that temp token can't access protected routes
            response = await client.get("/api/channels", 
                headers={"Authorization": f"Bearer {login_data['temp_token']}"})
            assert response.status_code == 401
            
            # Test invalid 2FA code
            response = await client.post("/api/auth/verify-2fa",
                json={"totp_code": "000000"},
                headers={"Authorization": f"Bearer {login_data['temp_token']}"})
            assert response.status_code == 401
            assert "Invalid TOTP code" in response.json()["detail"]
    finally:
        # Restore original test mode
        if original_test_mode is not None:
            os.environ["TEST_MODE"] = original_test_mode
        else:
            del os.environ["TEST_MODE"]

async def test_duplicate_registration(client: AsyncClient):
    """Test registration with duplicate email"""
    # Register first user
    response = await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "password123",
        "display_name": "Test User"
    })
    assert response.status_code == 201
    
    # Try to register same email again
    response = await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "differentpassword",
        "display_name": "Different User"
    })
    assert response.status_code == 400
    assert "Email already registered" in response.json()["detail"]

async def test_special_characters(client: AsyncClient):
    """Test registration and login with special characters"""
    test_cases = [
        {
            "email": "test.user+tag@example.com",
            "password": "password123!@#$%^&*()",
            "display_name": "Test 👨‍💻 User"
        },
        {
            "email": "üser@example.com",
            "password": "password123",
            "display_name": "Über User 🚀"
        }
    ]
    
    for user_data in test_cases:
        # Test registration
        response = await client.post("/api/auth/register", json=user_data)
        assert response.status_code == 201
        
        # Test login
        response = await client.post("/api/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })
        assert response.status_code == 200

async def test_token_validation(client: AsyncClient):
    """Test token validation and security"""
    # Register and get initial tokens
    await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "password123",
        "display_name": "Test User"
    })
    
    login_response = await client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "password123"
    })
    tokens = login_response.json()
    
    # Test using refresh token as access token (should fail)
    response = await client.get("/api/channels", 
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert response.status_code == 401
    assert "Could not validate credentials" in response.json()["detail"]
    
    # Test using access token for refresh (should fail)
    response = await client.post("/api/auth/refresh", 
        json={"refresh_token": tokens['access_token']})
    assert response.status_code == 401
    assert "Invalid refresh token" in response.json()["detail"]
    
    # Test refresh token reuse
    # First refresh is valid
    refresh_response = await client.post("/api/auth/refresh", 
        json={"refresh_token": tokens['refresh_token']})
    assert refresh_response.status_code == 200
    
    # Second refresh with same token should fail
    reuse_response = await client.post("/api/auth/refresh", 
        json={"refresh_token": tokens['refresh_token']})
    assert reuse_response.status_code == 401
    assert "Refresh token has been used" in reuse_response.json()["detail"]

if __name__ == "__main__":
    asyncio.run(test_auth_flow()) 