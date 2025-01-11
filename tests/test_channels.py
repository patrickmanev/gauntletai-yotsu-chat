import pytest
from httpx import AsyncClient
from typing import Dict, Any
import asyncio
from tests.conftest import register_test_user
from yotsu_chat.core.config import get_settings
from yotsu_chat.utils import debug_log

pytestmark = pytest.mark.asyncio

# Get settings instance
settings = get_settings()

async def test_channel_creation(client: AsyncClient):
    """Test channel creation functionality:
    1. Basic creation of public/private channels
    2. Name validation
    3. Initial member addition
    4. Error cases for invalid names/types
    5. Maximum name length validation
    6. Timestamp verification
    7. Invalid member handling
    """
    print("\n1. Setting up test users...")
    
    # Create test users
    user1 = await register_test_user(
        client,
        email="create_test1@example.com",
        password="Password1234!",
        display_name="CreateUser One"
    )
    
    user2 = await register_test_user(
        client,
        email="create_test2@example.com",
        password="Password1234!",
        display_name="CreateUser Two"
    )
    
    print("\n2. Testing public channel creation...")
    # Create a public channel with no initial members
    response = await client.post(
        "/api/channels",
        json={
            "name": "test-public-solo",
            "type": "public"
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201, f"Public channel creation failed: {response.text}"
    public_solo = response.json()
    assert public_solo["type"] == "public"
    
    # Verify creator is the only member
    response = await client.get(
        f"/api/members/{public_solo['channel_id']}",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    members = response.json()
    assert len(members) == 1, "Should only have creator as member"
    assert members[0]["user_id"] == user1["user_id"], "Creator should be the only member"
    assert members[0]["role"] is None, "Public channel members should not have roles"
    
    # Create a public channel with initial members (existing test)
    response = await client.post(
        "/api/channels",
        json={
            "name": "test-public-channel",
            "type": "public",
            "initial_members": [user2["user_id"]]
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201, f"Public channel creation failed: {response.text}"
    public_channel = response.json()
    assert public_channel["type"] == "public"
    
    # Verify timestamp exists and is in the correct format
    assert "created_at" in public_channel, "Channel should have a creation timestamp"
    from datetime import datetime
    creation_time = datetime.fromisoformat(public_channel["created_at"].replace('Z', '+00:00'))
    assert (datetime.utcnow() - creation_time).total_seconds() < 60, "Channel creation time should be recent"
    
    print("\n3. Testing private channel creation...")
    # Create a private channel with no initial members
    response = await client.post(
        "/api/channels",
        json={
            "name": "test-private-solo",
            "type": "private"
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201, f"Private channel creation failed: {response.text}"
    private_solo = response.json()
    assert private_solo["type"] == "private"
    
    # Verify creator is the only member and has OWNER role
    response = await client.get(
        f"/api/members/{private_solo['channel_id']}",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    members = response.json()
    assert len(members) == 1, "Should only have creator as member"
    assert members[0]["user_id"] == user1["user_id"], "Creator should be the only member"
    assert members[0]["role"] == "owner", "Creator should be assigned OWNER role in private channel"
    
    # Create a private channel with initial members (existing test)
    response = await client.post(
        "/api/channels",
        json={
            "name": "test-private-channel",
            "type": "private",
            "initial_members": [user2["user_id"]]
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201, f"Private channel creation failed: {response.text}"
    private_channel = response.json()
    assert private_channel["type"] == "private"
    
    print("\n4. Testing channel name constraints...")
    # Test missing name
    response = await client.post(
        "/api/channels",
        json={
            "type": "public",
            "initial_members": [user2["user_id"]]
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 422, "Expected error when name is missing"
    
    # Test invalid name format
    response = await client.post(
        "/api/channels",
        json={
            "name": "Invalid Name!",
            "type": "public",
            "initial_members": [user2["user_id"]]
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 422, "Expected error for invalid channel name format"
    
    # Test maximum name length (25 max, 26 characters is too much)
    long_name = "a" * 26
    response = await client.post(
        "/api/channels",
        json={
            "name": long_name,
            "type": "public"
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 422, "Expected error for name exceeding maximum length"
    errors = response.json()["detail"]
    debug_log("TEST", f"Validation errors: {errors}")
    assert isinstance(errors, list), "Validation errors should be a list"
    assert any("channel name cannot exceed 25 characters" in error["msg"].lower()
              for error in errors), "Expected max length validation error"
    
    print("\n5. Testing invalid member handling...")
    # Test with non-existent user ID
    response = await client.post(
        "/api/channels",
        json={
            "name": "invalid-members-test",
            "type": "public",
            "initial_members": [99999]  # Non-existent user ID
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 400, "Expected error for invalid member ID"
    assert "does not exist" in response.json()["detail"].lower(), "Expected error about non-existent user"
    
    # Test with duplicate members in initial_members
    response = await client.post(
        "/api/channels",
        json={
            "name": "duplicate-members-test",
            "type": "public",
            "initial_members": [user2["user_id"], user2["user_id"]]
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 400, "Expected error for duplicate members"
    assert "duplicate" in response.json()["detail"].lower()
    
    # Verify initial members were added
    response = await client.get(
        f"/api/members/{public_channel['channel_id']}",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    members = response.json()
    assert len(members) == 2, "Should have creator and one initial member"
    member_ids = {m["user_id"] for m in members}
    assert user1["user_id"] in member_ids, "Creator should be a member"
    assert user2["user_id"] in member_ids, "Initial member should be added"

async def test_public_channel_operations(client: AsyncClient):
    """Test public channel operations:
    1. Member addition/removal
    2. Verify no role management
    3. Public channel visibility
    4. Channel name updates by members
    """
    print("\n1. Setting up test users...")
    
    # Create test users
    user1 = await register_test_user(
        client,
        email="pub_test1@example.com",
        password="Password1234!",
        display_name="PubUser One"
    )
    
    user2 = await register_test_user(
        client,
        email="pub_test2@example.com",
        password="Password1234!",
        display_name="PubUser Two"
    )
    
    user3 = await register_test_user(
        client,
        email="pub_test3@example.com",
        password="Password1234!",
        display_name="PubUser Three"
    )
    
    print("\n2. Creating test public channel...")
    response = await client.post(
        "/api/channels",
        json={
            "name": "test-public",
            "type": "public"
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201
    public_channel = response.json()
    
    print("\n3. Testing member addition...")
    # Any user can add members to public channel
    response = await client.post(
        f"/api/members/{public_channel['channel_id']}",
        json={"user_id": user2["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201, "Failed to add member to public channel"
    
    # Even non-members can add members
    response = await client.post(
        f"/api/members/{public_channel['channel_id']}",
        json={"user_id": user3["user_id"]},
        headers={"Authorization": f"Bearer {user3['access_token']}"}
    )
    assert response.status_code == 201, "Non-members should be able to add members to public channel"
    
    print("\n4. Testing duplicate member prevention...")
    # Try to add the same user again
    response = await client.post(
        f"/api/members/{public_channel['channel_id']}",
        json={"user_id": user2["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 400, "Should not be able to add the same member twice"
    assert "already a member" in response.json()["detail"].lower()
    
    print("\n5. Testing member removal...")
    # Members can leave at any time
    response = await client.delete(
        f"/api/members/{public_channel['channel_id']}/{user2['user_id']}",
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 200, "Members should be able to leave public channels"
    
    # Add user2 back for testing removal by another member
    response = await client.post(
        f"/api/members/{public_channel['channel_id']}",
        json={"user_id": user2["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201, "Failed to add member back to public channel"
    
    # Test removal by another member
    response = await client.delete(
        f"/api/members/{public_channel['channel_id']}/{user2['user_id']}",
        headers={"Authorization": f"Bearer {user3['access_token']}"}
    )
    assert response.status_code == 200, "Any member should be able to remove other members from public channels"
    
    # Verify member was removed
    response = await client.get(
        f"/api/members/{public_channel['channel_id']}",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    members = response.json()
    member_ids = {m["user_id"] for m in members}
    assert user2["user_id"] not in member_ids, "Member should have been removed"
    
    print("\n6. Testing channel visibility...")
    # Public channels should be visible to all users
    response = await client.get(
        f"/api/channels/{public_channel['channel_id']}",
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 200, "Public channels should be visible to non-members"

    print("\n7. Testing channel name updates...")
    # Verify public channel names cannot be updated by members
    response = await client.patch(
        f"/api/channels/{public_channel['channel_id']}",
        json={"name": "updated-public-channel"},
        headers={"Authorization": f"Bearer {user3['access_token']}"}
    )
    assert response.status_code == 422, "Public channel names should not be updatable"
    errors = response.json()["detail"]
    assert any("only private channel names can be updated" in error["msg"].lower() for error in errors)

    # Verify public channel names cannot be updated by non-members
    response = await client.patch(
        f"/api/channels/{public_channel['channel_id']}",
        json={"name": "updated-by-non-member"},
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 422, "Public channel names should not be updatable"
    errors = response.json()["detail"]
    assert any("only private channel names can be updated" in error["msg"].lower() for error in errors)

    # Verify original name remains unchanged
    response = await client.get(
        f"/api/channels/{public_channel['channel_id']}",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "test-public", "Public channel name should remain unchanged"

    # Test duplicate channel name
    response = await client.post(
        "/api/channels",
        json={
            "name": "unique-public-channel",
            "type": "public"
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201
    
    response = await client.patch(
        f"/api/channels/{public_channel['channel_id']}",
        json={"name": "unique-public-channel"},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 400, "Should not allow duplicate channel names"
    assert "already exists" in response.json()["detail"].lower()

async def test_notes_channel_operations(client: AsyncClient):
    """Test notes channel operations:
    1. Notes channel creation during registration
    2. Member management restrictions
    3. Access control
    """
    print("\n1. Setting up test users...")
    
    # Create test users
    user1 = await register_test_user(
        client,
        email="notes_test1@example.com",
        password="Password1234!",
        display_name="NotesUser One"
    )
    
    user2 = await register_test_user(
        client,
        email="notes_test2@example.com",
        password="Password1234!",
        display_name="NotesUser Two"
    )
    
    print("\n2. Getting user's notes channel...")
    # Get user1's Notes channel
    response = await client.get(
        "/api/channels",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    channels = response.json()
    notes_channels = [c for c in channels if c["type"] == "notes"]
    assert len(notes_channels) == 1, "User should have exactly one Notes channel"
    notes_channel = notes_channels[0]
    
    print("\n3. Testing member management restrictions...")
    # Try to add a member to Notes channel
    response = await client.post(
        f"/api/members/{notes_channel['channel_id']}", 
        json={"user_id": user2["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 400, "Should not be able to add members to Notes channel"
    assert "Can only add members to public/private channels" in response.json()["detail"]
    
    print("\n4. Testing access control...")
    # Other users should not be able to see the notes channel
    response = await client.get(
        f"/api/channels/{notes_channel['channel_id']}",
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 404, "Notes channels should not be visible to other users"

    print("\n5. Testing self-removal restriction...")
    # Try to remove self from Notes channel
    response = await client.delete(
        f"/api/members/{notes_channel['channel_id']}/{user1['user_id']}",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 400, "Should not be able to leave Notes channel"
    assert "cannot remove members from notes" in response.json()["detail"].lower()

    print("\n6. Testing channel listing order...")
    # Get all user's channels and verify Notes channel is listed first
    response = await client.get(
        "/api/channels",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    channels = response.json()
    assert len(channels) > 0, "User should have at least one channel"
    assert channels[0]["type"] == "notes", "Notes channel should be listed first"
    assert channels[0]["channel_id"] == notes_channel["channel_id"]

    print("\n7. Testing name update restriction...")
    # Try to update Notes channel name
    response = await client.patch(
        f"/api/channels/{notes_channel['channel_id']}",
        json={"name": "my-notes"},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 400, "Should not be able to update Notes channel name"
    assert "cannot update notes channels" in response.json()["detail"].lower()

async def test_ownership_transfer(client: AsyncClient):
    """Test channel ownership transfer:
    1. Transfer ownership flow
    2. Role changes during transfer
    3. Validation rules
    """
    print("\n1. Setting up test users...")
    
    # Create test users
    user1 = await register_test_user(
        client,
        email="transfer_test1@example.com",
        password="Password1234!",
        display_name="TransferUser One"
    )
    
    user2 = await register_test_user(
        client,
        email="transfer_test2@example.com",
        password="Password1234!",
        display_name="TransferUser Two"
    )
    
    user3 = await register_test_user(
        client,
        email="transfer_test3@example.com",
        password="Password1234!",
        display_name="TransferUser Three"
    )
    
    print("\n2. Creating test private channel...")
    # Create a private channel
    response = await client.post(
        "/api/channels",
        json={
            "name": "transfer-test-channel",
            "type": "private",
            "initial_members": [user2["user_id"]]
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201
    private_channel = response.json()
    
    print("\n3. Testing ownership transfer...")
    # Transfer ownership to user2
    response = await client.post(
        f"/api/members/{private_channel['channel_id']}/transfer",
        json={"user_id": user2["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200, "Failed to transfer private channel ownership"
    
    # Verify new ownership roles
    response = await client.get(
        f"/api/members/{private_channel['channel_id']}",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    members = response.json()
    owner = next(m for m in members if m["user_id"] == user2["user_id"])
    old_owner = next(m for m in members if m["user_id"] == user1["user_id"])
    assert owner["role"] == "owner", "New owner should have owner role"
    assert old_owner["role"] == "admin", "Old owner should become admin"
    
    print("\n4. Testing transfer validation rules...")
    # Verify old owner cannot transfer ownership anymore
    response = await client.post(
        f"/api/members/{private_channel['channel_id']}/transfer",
        json={"user_id": user3["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 400, "Old owner should not be able to transfer ownership"
    
    # Try to transfer to non-member (should fail)
    response = await client.post(
        f"/api/members/{private_channel['channel_id']}/transfer",
        json={"user_id": user3["user_id"]},
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 400, "Should not be able to transfer ownership to non-member"
    
    print("\n5. Testing post-transfer permissions...")
    # Old owner (now admin) can still add members
    response = await client.post(
        f"/api/members/{private_channel['channel_id']}",
        json={"user_id": user3["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201, "Admin (old owner) should still be able to add members"
    
    # But cannot modify roles
    response = await client.put(
        f"/api/members/{private_channel['channel_id']}/{user3['user_id']}/role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 400, "Admin (old owner) should not be able to modify roles"

    print("\n6. Testing transfer back to previous owner...")
    # Transfer ownership back to user1 (previous owner)
    response = await client.post(
        f"/api/members/{private_channel['channel_id']}/transfer",
        json={"user_id": user1["user_id"]},
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 200, "Should be able to transfer ownership back to previous owner"
    
    # Verify roles after transfer back
    response = await client.get(
        f"/api/members/{private_channel['channel_id']}",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    members = response.json()
    new_owner = next(m for m in members if m["user_id"] == user1["user_id"])
    old_owner = next(m for m in members if m["user_id"] == user2["user_id"])
    assert new_owner["role"] == "owner", "Previous owner should become owner again"
    assert old_owner["role"] == "admin", "Previous owner should become admin"

    print("\n7. Testing transfer to admin vs regular member...")
    # Make user3 an admin
    response = await client.put(
        f"/api/members/{private_channel['channel_id']}/{user3['user_id']}/role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200, "Should be able to promote member to admin"

    # Transfer to admin (user3)
    response = await client.post(
        f"/api/members/{private_channel['channel_id']}/transfer",
        json={"user_id": user3["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200, "Should be able to transfer ownership to admin"

    print("\n8. Testing transfer with no other members...")
    # Create a new private channel with no other members
    response = await client.post(
        "/api/channels",
        json={
            "name": "solo-channel",
            "type": "private"
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201
    solo_channel = response.json()

    # Attempt to transfer ownership
    response = await client.post(
        f"/api/members/{solo_channel['channel_id']}/transfer",
        json={"user_id": user2["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 400, "Should not be able to transfer ownership with no other members"
    assert "no other members" in response.json()["detail"].lower()

    print("\n9. Testing concurrent transfer attempts...")
    # Create a new channel for concurrent transfer testing
    response = await client.post(
        "/api/channels",
        json={
            "name": "concurrent-test",
            "type": "private",
            "initial_members": [user2["user_id"], user3["user_id"]]
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201
    concurrent_channel = response.json()

    # Start first transfer
    import asyncio
    transfer1 = client.post(
        f"/api/members/{concurrent_channel['channel_id']}/transfer",
        json={"user_id": user2["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    
    # Attempt concurrent transfer
    transfer2 = client.post(
        f"/api/members/{concurrent_channel['channel_id']}/transfer",
        json={"user_id": user3["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    
    # Wait for both transfers to complete
    response1, response2 = await asyncio.gather(transfer1, transfer2)
    
    # One should succeed and one should fail
    assert (response1.status_code == 200 and response2.status_code == 400) or \
           (response1.status_code == 400 and response2.status_code == 200), \
           "One transfer should succeed and one should fail"
    
    if response2.status_code == 400:
        assert "transfer in progress" in response2.json()["detail"].lower()
    else:
        assert "transfer in progress" in response1.json()["detail"].lower()

async def test_private_channel_operations(client: AsyncClient):
    """Test private channel operations:
    1. Role hierarchy
    2. Role management rules
    3. Member removal rules
    4. Channel name update restrictions
    5. Single owner constraint
    """
    print("\n1. Setting up test users...")
    
    # Create test users
    user1 = await register_test_user(
        client,
        email="priv_test1@example.com",
        password="Password1234!",
        display_name="PrivUser One"
    )
    
    user2 = await register_test_user(
        client,
        email="priv_test2@example.com",
        password="Password1234!",
        display_name="PrivUser Two"
    )
    
    user3 = await register_test_user(
        client,
        email="priv_test3@example.com",
        password="Password1234!",
        display_name="PrivUser Three"
    )
    
    print("\n2. Creating test private channel...")
    response = await client.post(
        "/api/channels",
        json={
            "name": "test-private",
            "type": "private",
            "initial_members": [user2["user_id"]]
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201
    private_channel = response.json()
    
    print("\n3. Testing single owner constraint...")
    # Verify initial state - user1 should be owner
    response = await client.get(
        f"/api/members/{private_channel['channel_id']}",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    members = response.json()
    owner = next(m for m in members if m["user_id"] == user1["user_id"])
    assert owner["role"] == "owner", "Channel creator should be owner"
    
    # Try to promote another user to owner (should fail)
    response = await client.put(
        f"/api/members/{private_channel['channel_id']}/{user2['user_id']}/role",
        json={"role": "owner"},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 400, "Should not be able to have multiple owners"
    assert "can only have one owner" in response.json()["detail"].lower()
    
    # Verify user2 is still not owner
    response = await client.get(
        f"/api/members/{private_channel['channel_id']}",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    members = response.json()
    member = next(m for m in members if m["user_id"] == user2["user_id"])
    assert member["role"] == "member", "Failed promotion attempt should not change role"
    
    print("\n4. Testing ownership transfer atomicity...")
    # Add user3 to channel
    response = await client.post(
        f"/api/members/{private_channel['channel_id']}",
        json={"user_id": user3["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201
    
    # Try concurrent ownership transfers (should maintain single owner)
    import asyncio
    transfer1 = client.post(
        f"/api/members/{private_channel['channel_id']}/transfer",
        json={"user_id": user2["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    transfer2 = client.post(
        f"/api/members/{private_channel['channel_id']}/transfer",
        json={"user_id": user3["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    
    # Wait for both transfers to complete
    response1, response2 = await asyncio.gather(transfer1, transfer2)
    
    # One should succeed and one should fail
    assert (response1.status_code == 200 and response2.status_code == 400) or \
           (response1.status_code == 400 and response2.status_code == 200), \
           "One transfer should succeed and one should fail"
    
    # Verify we still have exactly one owner
    response = await client.get(
        f"/api/members/{private_channel['channel_id']}",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    members = response.json()
    owners = [m for m in members if m["role"] == "owner"]
    assert len(owners) == 1, "Should have exactly one owner after concurrent transfers"
    
    print("\n5. Testing channel name update restrictions...")
    # Remove user3 from channel first to test non-member access
    response = await client.delete(
        f"/api/members/{private_channel['channel_id']}/{user3['user_id']}",
        headers={"Authorization": f"Bearer {user2['access_token']}"}  # user2 is now owner
    )
    assert response.status_code == 200, "Failed to remove user3 from channel"

    # Only owner should be able to update private channel name
    response = await client.patch(
        f"/api/channels/{private_channel['channel_id']}",
        json={"name": "updated-by-owner"},
        headers={"Authorization": f"Bearer {user2['access_token']}"}  # user2 is now owner
    )
    assert response.status_code == 200, "Owner should be able to update private channel name"
    assert response.json()["name"] == "updated-by-owner"

    # Admin (old owner) should not be able to update channel name
    response = await client.patch(
        f"/api/channels/{private_channel['channel_id']}",
        json={"name": "updated-by-admin"},
        headers={"Authorization": f"Bearer {user1['access_token']}"}  # user1 is now admin
    )
    assert response.status_code == 403, "Admins should not be able to update private channel name"
    assert "only channel owners" in response.json()["detail"].lower()

    # Non-member should get 404 when trying to update
    response = await client.patch(
        f"/api/channels/{private_channel['channel_id']}",
        json={"name": "updated-by-non-member"},
        headers={"Authorization": f"Bearer {user3['access_token']}"}  # user3 is now a non-member
    )
    assert response.status_code == 404, "Non-members should not be able to see or update private channel"

if __name__ == "__main__":
    asyncio.run(test_channel_creation())
    asyncio.run(test_public_channel_operations())
    asyncio.run(test_notes_channel_operations())
    asyncio.run(test_ownership_transfer()) 