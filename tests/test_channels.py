import pytest
from httpx import AsyncClient
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
        "/api/members",
        params={"channel_ids": [public_solo['channel_id']]},
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
        "/api/members",
        params={"channel_ids": [private_solo['channel_id']]},
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
    assert "cannot add non-existent users" in response.json()["detail"].lower(), "Expected error about non-existent user"
    
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
        "/api/members",
        params={"channel_ids": [public_channel['channel_id']]},
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
    # Any member can add other members to public channel
    response = await client.post(
        f"/api/members/{public_channel['channel_id']}/members",
        json={"user_ids": [user2["user_id"]]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201, "Failed to add member to public channel"

    # Verify user3 is not a member
    response = await client.get(
        "/api/channels",
        params={"types": ["public"]},
        headers={"Authorization": f"Bearer {user3['access_token']}"}
    )
    assert response.status_code == 200, "Failed to list channels"
    channels = response.json()
    # User3 should not see the channel in their list since they're not a member
    assert not any(c["channel_id"] == public_channel["channel_id"] for c in channels), "User3 should not be a member of the channel"

    # Non-members cannot add other members
    response = await client.post(
        f"/api/members/{public_channel['channel_id']}/members",
        json={"user_ids": [user2["user_id"]]},
        headers={"Authorization": f"Bearer {user3['access_token']}"}
    )
    assert response.status_code == 403, "Non-members should not be able to add members to public channel"
    assert "must be a member" in response.json()["detail"]["message"].lower()
    
    # But anyone can add themselves to a public channel
    response = await client.post(
        f"/api/members/{public_channel['channel_id']}/members",
        json={"user_ids": [user3["user_id"]]},
        headers={"Authorization": f"Bearer {user3['access_token']}"}
    )
    assert response.status_code == 201, "Users should be able to add themselves to public channels"
    
    print("\n4. Testing duplicate member prevention...")
    # Try to add the same user again
    response = await client.post(
        f"/api/members/{public_channel['channel_id']}/members",
        json={"user_ids": [user2["user_id"]]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 400, "Should not be able to add the same member twice"
    assert "are already members" in response.json()["detail"].lower()
    
    print("\n5. Testing member removal...")
    # Members can leave at any time
    response = await client.delete(
        f"/api/members/{public_channel['channel_id']}/{user2['user_id']}",
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 204, "Members should be able to leave public channels"
    
    # Add user2 back for testing removal by another member
    response = await client.post(
        f"/api/members/{public_channel['channel_id']}/members",
        json={"user_ids": [user2["user_id"]]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201, "Failed to add member back to public channel"
    
    # Test removal by another member
    response = await client.delete(
        f"/api/members/{public_channel['channel_id']}/{user2['user_id']}",
        headers={"Authorization": f"Bearer {user3['access_token']}"}
    )
    assert response.status_code == 204, "Any member should be able to remove other members from public channels"
    
    # Verify member was removed
    response = await client.get(
        "/api/members",
        params={"channel_ids": [public_channel['channel_id']]},
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
    # 1. Verify public channels cannot be updated
    response = await client.patch(
        f"/api/channels/{public_channel['channel_id']}",
        json={"name": "updated-public-channel"},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 422, "Public channel names should not be updatable"
    errors = response.json()["detail"]
    assert any("Only private channel names can be updated" in error["msg"] for error in errors)

    # Verify original name remains unchanged
    response = await client.get(
        f"/api/channels/{public_channel['channel_id']}",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "test-public", "Public channel name should remain unchanged"

    # 2. Test private channel update permissions
    # Create a private channel
    response = await client.post(
        "/api/channels",
        json={
            "name": "test-private",
            "type": "private"
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201
    private_channel = response.json()

    # Add user2 as a member (not owner)
    response = await client.post(
        f"/api/members/{private_channel['channel_id']}/members",
        json={"user_ids": [user2["user_id"]]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201

    # Non-owner cannot update name
    response = await client.patch(
        f"/api/channels/{private_channel['channel_id']}",
        json={"name": "updated-by-member"},
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 403, "Only owners should be able to update private channel names"
    assert "only channel owners" in response.json()["detail"].lower()

    # Owner can update name
    response = await client.patch(
        f"/api/channels/{private_channel['channel_id']}",
        json={"name": "updated-by-owner"},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200, "Channel owner should be able to update private channel name"
    assert response.json()["name"] == "updated-by-owner"

    # 3. Test duplicate names
    # Create another private channel
    response = await client.post(
        "/api/channels",
        json={
            "name": "another-private",
            "type": "private"
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201
    another_private = response.json()

    # Try to update to an existing name
    response = await client.patch(
        f"/api/channels/{another_private['channel_id']}",
        json={"name": "updated-by-owner"},  # Try to use the name we just set
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 422, "Should not allow duplicate channel names"
    errors = response.json()["detail"]
    assert any("already exists" in error["msg"] for error in errors)

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
        f"/api/members/{notes_channel['channel_id']}/members",
        json={"user_id": user2["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 422, "Should not be able to add members to Notes channel (notes channels are single-member only)"
    
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
    assert response.status_code == 422, "Should not be able to update Notes channel name"
    assert "only private channel names can be updated" in response.json()["detail"][0]["msg"].lower()

async def test_ownership_transfer(client: AsyncClient):
    """Test channel ownership transfer:
    1. Basic ownership transfer flow
    2. Role changes during transfer
    3. Validation rules and error cases
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
    
    print("\n2. Creating test channels...")
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
    
    # Create a public channel (for testing channel type validation)
    response = await client.post(
        "/api/channels",
        json={
            "name": "public-channel",
            "type": "public",
            "initial_members": [user2["user_id"]]
        },
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 201
    public_channel = response.json()
    
    print("\n3. Testing successful ownership transfer...")
    # Transfer ownership to user2
    response = await client.post(
        f"/api/members/{private_channel['channel_id']}/transfer",
        json={"user_id": user2["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Channel ownership transferred successfully"
    
    # Verify new ownership roles
    response = await client.get(
        "/api/members",
        params={"channel_ids": [private_channel['channel_id']]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    members = response.json()
    owner = next(m for m in members if m["user_id"] == user2["user_id"])
    old_owner = next(m for m in members if m["user_id"] == user1["user_id"])
    assert owner["role"] == "owner"
    assert old_owner["role"] == "admin"
    
    print("\n4. Testing validation rules...")
    # Test: Cannot transfer ownership in public channels
    response = await client.post(
        f"/api/members/{public_channel['channel_id']}/transfer",
        json={"user_id": user2["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 400
    assert "only be transferred in private channels" in response.json()["detail"].lower()
    
    # Test: Non-owner cannot transfer ownership
    response = await client.post(
        f"/api/members/{private_channel['channel_id']}/transfer",
        json={"user_id": user3["user_id"]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 400
    assert "only the current owner" in response.json()["detail"].lower()
    
    # Test: Cannot transfer to non-member
    response = await client.post(
        f"/api/members/{private_channel['channel_id']}/transfer",
        json={"user_id": user3["user_id"]},
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 400
    assert "must be a member" in response.json()["detail"].lower()
    
    print("\n5. Testing post-transfer permissions...")
    # Add user3 as a member for further testing
    response = await client.post(
        f"/api/members/{private_channel['channel_id']}/members",
        json={"user_ids": [user3["user_id"]]},
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 201
    
    # Test: Only owner can promote members
    response = await client.put(
        f"/api/members/{private_channel['channel_id']}/{user3['user_id']}/promote",
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 422
    assert any("only the owner can modify roles" in error["msg"].lower() for error in response.json()["detail"])
    
    # Test: New owner can promote members
    response = await client.put(
        f"/api/members/{private_channel['channel_id']}/{user3['user_id']}/promote",
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Member promoted to admin"
    assert response.json()["user_id"] == user3["user_id"]
    
    # Verify the promotion was successful
    response = await client.get(
        "/api/members",
        params={"channel_ids": [private_channel['channel_id']]},
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 200
    members = response.json()
    promoted_member = next(m for m in members if m["user_id"] == user3["user_id"])
    assert promoted_member["role"] == "admin"
    
    # Test: New owner can demote admins
    response = await client.put(
        f"/api/members/{private_channel['channel_id']}/{user3['user_id']}/demote",
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Admin demoted to member"
    assert response.json()["user_id"] == user3["user_id"]
    
    # Verify the demotion was successful
    response = await client.get(
        "/api/members",
        params={"channel_ids": [private_channel['channel_id']]},
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 200
    members = response.json()
    demoted_member = next(m for m in members if m["user_id"] == user3["user_id"])
    assert demoted_member["role"] == "member"
    
    print("\n6. Testing transfer back to previous owner...")
    # Transfer ownership back to user1
    response = await client.post(
        f"/api/members/{private_channel['channel_id']}/transfer",
        json={"user_id": user1["user_id"]},
        headers={"Authorization": f"Bearer {user2['access_token']}"}
    )
    assert response.status_code == 200
    
    # Verify final roles
    response = await client.get(
        "/api/members",
        params={"channel_ids": [private_channel['channel_id']]},
        headers={"Authorization": f"Bearer {user1['access_token']}"}
    )
    assert response.status_code == 200
    members = response.json()
    final_owner = next(m for m in members if m["user_id"] == user1["user_id"])
    final_admin = next(m for m in members if m["user_id"] == user2["user_id"])
    assert final_owner["role"] == "owner"
    assert final_admin["role"] == "admin"


if __name__ == "__main__":
    asyncio.run(test_channel_creation())
    asyncio.run(test_public_channel_operations())
    asyncio.run(test_notes_channel_operations())
    asyncio.run(test_ownership_transfer()) 