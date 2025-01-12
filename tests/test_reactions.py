import pytest
from httpx import AsyncClient
from typing import Dict, Any
from yotsu_chat.core.config import get_settings

pytestmark = pytest.mark.asyncio

# Get settings instance
settings = get_settings()

async def test_basic_reactions(client: AsyncClient, access_token: str, test_message: Dict[str, Any]):
    """Test basic reaction operations including:
    1. Adding unique reactions
    2. Preventing duplicate reactions from same user
    3. Verifying reaction counts
    """
    message_id = test_message["message_id"]
    
    # Test adding reactions
    test_cases = [
        ("👍", 201, "Basic emoji"),
        ("🎉", 201, "Another basic emoji"),
        ("👍", 400, "Duplicate emoji from same user"),
        ("🤖", 201, "Third emoji"),
    ]
    
    for emoji, expected_status, description in test_cases:
        response = await client.post(
            f"/api/reactions/messages/{message_id}",
            json={"emoji": emoji},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == expected_status, f"Failed: {description}"
    
    # Test getting reactions
    response = await client.get(
        f"/api/reactions/messages/{message_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    reactions = response.json()
    assert len(reactions) == 3, "Should have 3 unique emojis"

async def test_reaction_limits(client: AsyncClient, access_token: str, test_message: Dict[str, Any]):
    """Test reaction limits including:
    1. Adding maximum allowed unique emojis
    2. Verifying limit enforcement
    3. Testing limit error messages
    """
    message_id = test_message["message_id"]
    
    # Add maximum allowed emojis
    emojis = ["👍", "🎉", "❤️", "😀", "😂", "😊", "😎", "😍", "🤔", "🤗", "🤓", "🤖"]
    assert len(emojis) == settings.reaction.max_unique_emojis, "Test data should match max reactions limit"
    
    for emoji in emojis:
        response = await client.post(
            f"/api/reactions/messages/{message_id}",
            json={"emoji": emoji},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201, f"Failed to add emoji {emoji}"
    
    # Try to add one more (should fail)
    response = await client.post(
        f"/api/reactions/messages/{message_id}",
        json={"emoji": "🚀"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 400
    assert f"Maximum number of unique emoji reactions ({settings.reaction.max_unique_emojis}) reached" in response.json()["detail"]

async def test_multi_user_reactions(
    client: AsyncClient,
    access_token: str,
    second_user_token: Dict[str, Any],
    test_message: Dict[str, Any]
):
    """Test reactions from multiple users including:
    1. Multiple users adding same reaction
    2. Reaction count verification
    3. User list in reaction details
    """
    message_id = test_message["message_id"]
    channel_id = test_message["channel_id"]

    # Add second user to the channel first
    response = await client.post(
        f"/api/members/{channel_id}",
        json={"user_id": second_user_token["user_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201

    # First user adds reaction
    response = await client.post(
        f"/api/reactions/messages/{message_id}",
        json={"emoji": "👍"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    
    # Second user adds same reaction
    response = await client.post(
        f"/api/reactions/messages/{message_id}",
        json={"emoji": "👍"},
        headers={"Authorization": f"Bearer {second_user_token['access_token']}"}
    )
    assert response.status_code == 201
    
    # Verify reaction count and user list
    response = await client.get(
        f"/api/reactions/messages/{message_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    reactions = response.json()
    thumbs_up = next(r for r in reactions if r["emoji"] == "👍")
    assert thumbs_up["count"] == 2, "Should show two users reacted"
    assert len(thumbs_up["users"]) == 2, "Should list both users who reacted"

async def test_reactions_cleanup_on_message_delete(
    client: AsyncClient,
    access_token: str,
    test_channel: Dict[str, Any]
):
    """Test reaction cleanup when messages are deleted including:
    1. Adding reactions to a message
    2. Verifying reactions exist
    3. Deleting message and verifying reaction cleanup
    """
    # Create a message
    message_response = await client.post(
        "/api/messages",
        json={"content": "Message to be deleted", "channel_id": test_channel["channel_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert message_response.status_code == 201
    message_id = message_response.json()["message_id"]
    
    # Add some reactions
    emojis = ["👍", "🎉", "❤️"]
    for emoji in emojis:
        response = await client.post(
            f"/api/reactions/messages/{message_id}",
            json={"emoji": emoji},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
    
    # Verify reactions exist
    response = await client.get(
        f"/api/reactions/messages/{message_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert len(response.json()) == len(emojis)
    
    # Delete the message
    delete_response = await client.delete(
        f"/api/messages/{message_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert delete_response.status_code == 204
    
    # Try to get reactions for the deleted message
    response = await client.get(
        f"/api/reactions/messages/{message_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 0, "All reactions should be gone"

async def test_reactions_cleanup_on_thread_parent_delete(
    client: AsyncClient,
    access_token: str,
    test_channel: Dict[str, Any]
):
    """Test reaction cleanup in threaded messages including:
    1. Creating parent and reply messages
    2. Adding reactions to both messages
    3. Deleting parent and verifying reaction behavior
    4. Verifying reply reactions remain intact
    """
    # Create parent message
    parent_response = await client.post(
        "/api/messages",
        json={"content": "Parent message", "channel_id": test_channel["channel_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert parent_response.status_code == 201
    parent_id = parent_response.json()["message_id"]

    # Create reply message
    reply_response = await client.post(
        "/api/messages",
        json={"content": "Reply message", "channel_id": test_channel["channel_id"], "parent_id": parent_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert reply_response.status_code == 201
    
    # Add reactions to both parent and reply
    for message_id in [parent_id, reply_response.json()["message_id"]]:
        response = await client.post(
            f"/api/reactions/messages/{message_id}",
            json={"emoji": "👍"},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
    
    # Delete parent message (should be marked as deleted but not actually deleted)
    delete_response = await client.delete(
        f"/api/messages/{parent_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert delete_response.status_code == 204
    
    # Verify parent message reactions are gone
    response = await client.get(
        f"/api/reactions/messages/{parent_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 0, "Parent reactions should be gone"
    
    # But reply reactions should still exist
    response = await client.get(
        f"/api/reactions/messages/{reply_response.json()['message_id']}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 1, "Reply reaction should still be there"

async def test_reaction_permissions(
    client: AsyncClient,
    access_token: str,
    second_user_token: Dict[str, Any],
    test_channel: Dict[str, Any]
):
    """Test reaction permissions across different channel types:
    1. Public channel - non-member cannot react
    2. Private channel - non-member cannot react
    3. DM channel - only participants can react
    4. Notes channel - only owner can react
    """
    # 1. Test public channel reactions
    print("\n1. Testing public channel reactions...")
    response = await client.post(
        "/api/messages",
        json={"content": "Public message", "channel_id": test_channel["channel_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    public_message = response.json()

    # Non-member should not be able to react
    response = await client.post(
        f"/api/reactions/messages/{public_message['message_id']}",
        json={"emoji": "👍"},
        headers={"Authorization": f"Bearer {second_user_token['access_token']}"}
    )
    assert response.status_code == 403
    print("Error response:", response.json())  # Debug print
    assert "Not a member of this channel" in response.json()["detail"]["message"]

    # 2. Test private channel reactions
    print("\n2. Testing private channel reactions...")
    response = await client.post(
        "/api/channels",
        json={"name": "test-private", "type": "private"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    private_channel = response.json()

    response = await client.post(
        "/api/messages",
        json={"content": "Private message", "channel_id": private_channel["channel_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    private_message = response.json()

    # Non-member should not be able to react
    response = await client.post(
        f"/api/reactions/messages/{private_message['message_id']}",
        json={"emoji": "👍"},
        headers={"Authorization": f"Bearer {second_user_token['access_token']}"}
    )
    assert response.status_code == 403
    assert "Not a member of this channel" in response.json()["detail"]["message"]

    # 3. Test DM channel reactions
    print("\n3. Testing DM channel reactions...")
    # Create DM by sending a message
    response = await client.post(
        "/api/messages",
        json={"content": "DM message", "recipient_id": second_user_token["user_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    dm_message = response.json()

    # Both participants should be able to react
    for token in [access_token, second_user_token["access_token"]]:
        response = await client.post(
            f"/api/reactions/messages/{dm_message['message_id']}",
            json={"emoji": "👍"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 201

    # 4. Test Notes channel reactions
    print("\n4. Testing Notes channel reactions...")
    # Get user's Notes channel
    response = await client.get(
        "/api/channels",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    notes_channel = next(ch for ch in response.json() if ch["type"] == "notes")

    # Create a note
    response = await client.post(
        "/api/messages",
        json={"content": "Note message", "channel_id": notes_channel["channel_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    note_message = response.json()

    # Other user should not be able to react to notes
    response = await client.post(
        f"/api/reactions/messages/{note_message['message_id']}",
        json={"emoji": "👍"},
        headers={"Authorization": f"Bearer {second_user_token['access_token']}"}
    )
    assert response.status_code == 403
    assert "Not a member of this channel" in response.json()["detail"]["message"] 