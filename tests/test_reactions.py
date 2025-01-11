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
        f"/api/messages/channels/{test_channel['channel_id']}",
        json={"content": "Message to be deleted"},
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
    assert delete_response.status_code == 200
    
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
        f"/api/messages/channels/{test_channel['channel_id']}",
        json={"content": "Parent message"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert parent_response.status_code == 201
    parent_data = parent_response.json()
    
    # Create reply
    reply_response = await client.post(
        f"/api/messages/channels/{test_channel['channel_id']}",
        json={
            "content": "Reply message",
            "thread_id": parent_data["message_id"]
        },
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert reply_response.status_code == 201
    reply_data = reply_response.json()
    
    # Add reactions to both parent and reply
    for message_id in [parent_data["message_id"], reply_data["message_id"]]:
        response = await client.post(
            f"/api/reactions/messages/{message_id}",
            json={"emoji": "👍"},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
    
    # Delete parent message (should be marked as deleted but not actually deleted)
    delete_response = await client.delete(
        f"/api/messages/{parent_data['message_id']}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert delete_response.status_code == 200
    
    # Verify parent message reactions are gone
    response = await client.get(
        f"/api/reactions/messages/{parent_data['message_id']}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 0, "Parent reactions should be gone"
    
    # But reply reactions should still exist
    response = await client.get(
        f"/api/reactions/messages/{reply_data['message_id']}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 1, "Reply reaction should still be there" 