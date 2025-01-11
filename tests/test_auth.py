import pytest
from httpx import AsyncClient
import os
import json
import asyncio
from datetime import datetime, timedelta
import pyotp
from jose import jwt
from contextlib import contextmanager

from yotsu_chat.core.config import get_settings, EnvironmentMode

pytestmark = pytest.mark.asyncio

# Get settings instance
settings = get_settings()

@contextmanager
def temp_env_mode(mode: EnvironmentMode):
    """Temporarily change the environment mode."""
    original_mode = os.getenv("YOTSU_ENVIRONMENT")
    os.environ["YOTSU_ENVIRONMENT"] = mode.value
    try:
        yield
    finally:
        if original_mode is not None:
            os.environ["YOTSU_ENVIRONMENT"] = original_mode
        else:
            del os.environ["YOTSU_ENVIRONMENT"]

async def test_auth_flow(client: AsyncClient):
    """Test the complete authentication flow"""
    # 1. Test registration
    print("\n1. Testing registration...")
    response = await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "Password1234!",
        "display_name": "Test User"
    })
    print(f"Registration response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    assert response.status_code == 201, "Registration failed"
    temp_token = response.json()["temp_token"]
    totp_uri = response.json()["totp_uri"]
    
    # Extract TOTP secret from URI
    totp_secret = pyotp.parse_uri(totp_uri).secret
    
    # Verify 2FA to complete registration
    print("\n1.5 Verifying 2FA for registration...")
    totp = pyotp.TOTP(totp_secret)
    verify_response = await client.post(
        "/api/auth/verify-2fa",
        json={"totp_code": totp.now()},
        headers={"Authorization": f"Bearer {temp_token}"}
    )
    print(f"2FA verification response: {verify_response.status_code}")
    print(json.dumps(verify_response.json(), indent=2))
    assert verify_response.status_code == 200, "2FA verification failed"
    
    # 2. Test login
    print("\n2. Testing login...")
    response = await client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "Password1234!"
    })
    print(f"Login response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    assert response.status_code == 200, "Login failed"
    
    # Check if we're in test mode (access token returned) or normal mode (temp token returned)
    response_data = response.json()
    if settings.is_test_mode:
        # Test mode - we already have the tokens
        access_token = response_data["access_token"]
        refresh_token = response_data["refresh_token"]
        assert access_token is not None, "Access token not returned"
        assert refresh_token is not None, "Refresh token not returned"
    else:
        # Normal mode - need to do 2FA
        temp_token = response_data["temp_token"]
        assert temp_token is not None, "Temp token not returned"
        
        # 3. Test 2FA verification for login
        print("\n3. Testing 2FA verification for login...")
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
        "password": "Password1234!"
    })
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]

    # Test wrong password
    # First register a user
    await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "Password1234!",
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
    # Temporarily switch to dev mode to test normal flow
    with temp_env_mode(EnvironmentMode.DEV):
        # Register and login
        register_response = await client.post("/api/auth/register", json={
            "email": "test@example.com",
            "password": "Password1234!",
            "display_name": "Test User"
        })
        assert register_response.status_code == 201
        temp_token = register_response.json()["temp_token"]
        totp_uri = register_response.json()["totp_uri"]
        totp_secret = pyotp.parse_uri(totp_uri).secret
        
        # Complete registration with 2FA
        totp = pyotp.TOTP(totp_secret)
        verify_response = await client.post(
            "/api/auth/verify-2fa",
            json={"totp_code": totp.now()},
            headers={"Authorization": f"Bearer {temp_token}"}
        )
        assert verify_response.status_code == 200
        
        login_response = await client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "Password1234!"
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

async def test_duplicate_registration(client: AsyncClient):
    """Test registration with duplicate email"""
    # Register first user
    response = await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "Password1234!",
        "display_name": "Test User"
    })
    assert response.status_code == 201
    temp_token = response.json()["temp_token"]
    totp_uri = response.json()["totp_uri"]
    totp_secret = pyotp.parse_uri(totp_uri).secret
    
    # Complete first registration with 2FA
    totp = pyotp.TOTP(totp_secret)
    verify_response = await client.post(
        "/api/auth/verify-2fa",
        json={"totp_code": totp.now()},
        headers={"Authorization": f"Bearer {temp_token}"}
    )
    assert verify_response.status_code == 200
    
    # Try to register same email again
    response = await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "Password1234!",
        "display_name": "Different User"
    })
    assert response.status_code == 400
    assert "Email already registered" in response.json()["detail"]

async def test_special_characters(client: AsyncClient):
    """Test registration and login with special characters"""
    test_cases = [
        {
            "email": "test.user+tag@example.com",
            "password": "Password1234!",
            "display_name": "John Smith"
        },
        {
            "email": "üser@example.com",
            "password": "Password1234!",
            "display_name": "Mary O'Connor"
        }
    ]
    
    for user_data in test_cases:
        # Test registration
        response = await client.post("/api/auth/register", json=user_data)
        assert response.status_code == 201
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
        assert verify_response.status_code == 200
        
        # Test login
        response = await client.post("/api/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })
        assert response.status_code == 200

async def test_token_validation(client: AsyncClient):
    """Test token validation and security"""
    # Register and get initial tokens
    register_response = await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "Password1234!",
        "display_name": "Test User"
    })
    assert register_response.status_code == 201
    temp_token = register_response.json()["temp_token"]
    totp_uri = register_response.json()["totp_uri"]
    totp_secret = pyotp.parse_uri(totp_uri).secret
    
    # Complete registration with 2FA
    totp = pyotp.TOTP(totp_secret)
    verify_response = await client.post(
        "/api/auth/verify-2fa",
        json={"totp_code": totp.now()},
        headers={"Authorization": f"Bearer {temp_token}"}
    )
    assert verify_response.status_code == 200
    
    login_response = await client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "Password1234!"
    })
    assert login_response.status_code == 200
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