import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_basic_reactions(client: AsyncClient, access_token: str, test_message: dict):
    """Test basic reaction operations"""
    message_id = test_message["message_id"]
    
    # Test adding reactions
    test_cases = [
        ("👍", 201),  # Basic emoji
        ("🎉", 201),  # Another basic emoji
        ("👍", 400),  # Duplicate emoji from same user
        ("🤖", 201),  # Third emoji
    ]
    
    for emoji, expected_status in test_cases:
        response = await client.post(
            f"/api/reactions/messages/{message_id}",
            json={"emoji": emoji},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == expected_status
    
    # Test getting reactions
    response = await client.get(
        f"/api/reactions/messages/{message_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    reactions = response.json()
    assert len(reactions) == 3  # Should have 3 unique emojis

async def test_reaction_limits(client: AsyncClient, access_token: str, test_message: dict):
    """Test reaction limits"""
    message_id = test_message["message_id"]
    
    # Add maximum allowed emojis
    emojis = ["👍", "🎉", "❤️", "😀", "😂", "😊", "😎", "😍", "🤔", "🤗", "🤓", "🤖"]
    for emoji in emojis:
        response = await client.post(
            f"/api/reactions/messages/{message_id}",
            json={"emoji": emoji},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 201
    
    # Try to add one more (should fail)
    response = await client.post(
        f"/api/reactions/messages/{message_id}",
        json={"emoji": "🚀"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 400
    assert "Maximum number of unique emoji reactions (12) reached" in response.json()["detail"]

async def test_multi_user_reactions(client: AsyncClient, access_token: str, second_user_token: dict, test_message: dict):
    """Test reactions from multiple users"""
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
    
    # Verify reaction count
    response = await client.get(
        f"/api/reactions/messages/{message_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    reactions = response.json()
    thumbs_up = next(r for r in reactions if r["emoji"] == "👍")
    assert thumbs_up["count"] == 2
    assert len(thumbs_up["users"]) == 2

async def test_reactions_cleanup_on_message_delete(client: AsyncClient, access_token: str, test_channel: dict):
    """Test that reactions are properly cleaned up when a message is deleted"""
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
    assert len(response.json()) == 0  # All reactions should be gone

async def test_reactions_cleanup_on_thread_parent_delete(client: AsyncClient, access_token: str, test_channel: dict):
    """Test reaction cleanup behavior when a thread parent message is deleted"""
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
    assert len(response.json()) == 0  # Parent reactions should be gone
    
    # But reply reactions should still exist
    response = await client.get(
        f"/api/reactions/messages/{reply_data['message_id']}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 1  # Reply reaction should still be there 