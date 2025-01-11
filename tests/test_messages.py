import pytest
from httpx import AsyncClient
from typing import Dict, Any, List
from pydantic import BaseModel
import json
from tests.conftest import register_test_user

pytestmark = pytest.mark.asyncio

# Pydantic models for request/response validation
class MessageCreate(BaseModel):
    content: str
    parent_id: int | None = None
    channel_id: int | None = None
    recipient_id: int | None = None

class MessageUpdate(BaseModel):
    content: str

class MessageResponse(BaseModel):
    message_id: int
    channel_id: int
    user_id: int
    content: str
    parent_id: int | None
    created_at: str
    edited_at: str | None
    display_name: str

class ChannelCreate(BaseModel):
    name: str | None = None
    type: str
    initial_members: List[int] | None = None

class ChannelResponse(BaseModel):
    channel_id: int
    name: str | None
    type: str
    created_at: str
    is_member: bool
    role: str | None = None

async def test_public_channel_message_operations(
    client: AsyncClient,
    access_token: str,
    second_user_token: Dict[str, Any],
    test_channel: Dict[str, Any]
) -> None:
    """Test message operations in a public channel"""
    channel_id: int = test_channel["channel_id"]
    
    # Add second user to the channel
    response = await client.post(
        f"/api/members/{channel_id}",
        json={"user_id": second_user_token["user_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    
    print("\n1. Testing message creation...")
    # Create a message
    message_create = MessageCreate(content="Test message", channel_id=channel_id)
    response = await client.post(
        "/api/messages",
        json=message_create.model_dump(),
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    message_data = MessageResponse(**response.json())
    assert message_data.content == "Test message"
    assert message_data.parent_id is None
    
    print("\n2. Testing message listing...")
    # Get messages
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    messages = [MessageResponse(**msg) for msg in response.json()]
    assert len(messages) == 1
    assert messages[0].message_id == message_data.message_id
    
    print("\n3. Testing message updates...")
    # Update message
    message_update = MessageUpdate(content="Updated message")
    response = await client.put(
        f"/api/messages/{message_data.message_id}",
        json=message_update.model_dump(),
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    updated_message = MessageResponse(**response.json())
    assert updated_message.content == "Updated message"
    
    # Try to update message as another user (should fail)
    response = await client.put(
        f"/api/messages/{message_data.message_id}",
        json=MessageUpdate(content="Unauthorized update").model_dump(),
        headers={"Authorization": f"Bearer {second_user_token['access_token']}"}
    )
    assert response.status_code == 403
    
    print("\n4. Testing message deletion...")
    # Delete message
    response = await client.delete(
        f"/api/messages/{message_data.message_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    
    # Verify message is deleted
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    messages = [MessageResponse(**msg) for msg in response.json()]
    assert len(messages) == 0

async def test_dm_channel_message_operations(
    client: AsyncClient,
    access_token: str,
    second_user_token: Dict[str, Any]
) -> None:
    """Test message operations in a DM channel"""
    print("\n1. Creating DM channel via message...")
    # Create DM channel by sending a message to the other user
    message_create = MessageCreate(
        content="DM test message",
        recipient_id=second_user_token["user_id"]
    )
    response = await client.post(
        "/api/messages",
        json=message_create.model_dump(),
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    message_data = MessageResponse(**response.json())
    
    print("\n2. Verifying both users can see the message...")
    # Verify both users can see the message
    for token in [access_token, second_user_token["access_token"]]:
        response = await client.get(
            f"/api/messages/channels/{message_data.channel_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        messages = [MessageResponse(**msg) for msg in response.json()]
        assert len(messages) == 1
        assert messages[0].message_id == message_data.message_id

async def test_notes_channel_message_operations(
    client: AsyncClient,
    access_token: str
) -> None:
    """Test message operations in a Notes channel"""
    print("\n1. Getting Notes channel...")
    # Get Notes channel (should be created during registration)
    response = await client.get(
        "/api/channels",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    channels = [ChannelResponse(**ch) for ch in response.json()]
    notes_channels = [c for c in channels if c.type == "notes"]
    assert len(notes_channels) == 1, "User should have exactly one Notes channel"
    notes_channel = notes_channels[0]
    
    print("\n2. Testing message creation in Notes...")
    # Create a message
    message_create = MessageCreate(content="Notes test message", channel_id=notes_channel.channel_id)
    response = await client.post(
        "/api/messages",
        json=message_create.model_dump(),
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    message_data = MessageResponse(**response.json())
    
    # Verify message is visible
    response = await client.get(
        f"/api/messages/channels/{notes_channel.channel_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    messages = [MessageResponse(**msg) for msg in response.json()]
    assert len(messages) == 1
    assert messages[0].message_id == message_data.message_id

async def test_thread_operations(
    client: AsyncClient,
    access_token: str,
    second_user_token: Dict[str, Any],
    test_channel: Dict[str, Any]
) -> None:
    """Test comprehensive thread operations"""
    channel_id: int = test_channel["channel_id"]
    
    print("\n1. Creating parent message...")
    # Create parent message
    parent_message = MessageCreate(content="Parent message", channel_id=channel_id)
    parent_response = await client.post(
        "/api/messages",
        json=parent_message.model_dump(),
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert parent_response.status_code == 201
    parent_data = MessageResponse(**parent_response.json())
    
    print("\n2. Testing thread replies...")
    # Create multiple replies
    replies: List[MessageResponse] = []
    for i in range(3):
        reply_message = MessageCreate(
            content=f"Reply message {i+1}",
            channel_id=channel_id,
            parent_id=parent_data.message_id
        )
        reply_response = await client.post(
            "/api/messages",
            json=reply_message.model_dump(),
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert reply_response.status_code == 201
        reply_data = MessageResponse(**reply_response.json())
        assert reply_data.parent_id == parent_data.message_id
        replies.append(reply_data)
    
    print("\n3. Testing thread visibility...")
    # Verify thread replies don't show up in main channel view
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    channel_messages = [MessageResponse(**msg) for msg in response.json()]
    assert len(channel_messages) == 1, "Only parent message should be visible in main view"
    assert channel_messages[0].message_id == parent_data.message_id
    
    # Get messages in thread
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"parent_id": parent_data.message_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    thread_messages = [MessageResponse(**msg) for msg in response.json()]
    assert len(thread_messages) == 3
    
    print("\n4. Testing thread pagination...")
    # Create more replies for pagination testing
    more_replies: List[MessageResponse] = []
    for i in range(7):  # Total 10 replies
        reply_message = MessageCreate(
            content=f"Paginated reply {i+1}",
            channel_id=channel_id,
            parent_id=parent_data.message_id
        )
        reply_response = await client.post(
            "/api/messages",
            json=reply_message.model_dump(),
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert reply_response.status_code == 201
        more_replies.append(MessageResponse(**reply_response.json()))
    
    # Test pagination (default limit is 50)
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={
            "parent_id": parent_data.message_id,
            "limit": 5
        },
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    first_page = [MessageResponse(**msg) for msg in response.json()]
    assert len(first_page) == 5, "Should return exactly 5 messages"
    
    # Get next page using before parameter
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={
            "parent_id": parent_data.message_id,
            "limit": 5,
            "before": first_page[-1].message_id
        },
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    second_page = [MessageResponse(**msg) for msg in response.json()]
    assert len(second_page) == 5, "Should return exactly 5 messages"
    assert all(m1.message_id > m2.message_id for m1, m2 in zip(first_page, second_page)), "Messages should be in descending order"
    
    print("\n5. Testing thread message validation...")
    # Try to create nested reply (should fail)
    nested_message = MessageCreate(
        content="Nested reply",
        channel_id=channel_id,
        parent_id=replies[0].message_id
    )
    nested_response = await client.post(
        "/api/messages",
        json=nested_message.model_dump(),
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert nested_response.status_code == 400
    assert "Cannot reply to a reply" in nested_response.json()["detail"]
    
    print("\n6. Testing thread permissions...")
    # Add second user to channel
    response = await client.post(
        f"/api/members/{channel_id}",
        json={"user_id": second_user_token["user_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    
    # Second user should be able to see and reply to thread
    reply_message = MessageCreate(
        content="Reply from second user",
        channel_id=channel_id,
        parent_id=parent_data.message_id
    )
    reply_response = await client.post(
        "/api/messages",
        json=reply_message.model_dump(),
        headers={"Authorization": f"Bearer {second_user_token['access_token']}"}
    )
    assert reply_response.status_code == 201
    
    print("\n7. Testing thread parent deletion...")
    # Delete parent message
    delete_response = await client.delete(
        f"/api/messages/{parent_data.message_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert delete_response.status_code == 200
    
    # Verify parent is soft-deleted but replies are still visible
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"parent_id": parent_data.message_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    thread_messages = [MessageResponse(**msg) for msg in response.json()]
    assert len(thread_messages) == 11  # 3 + 7 + 1 from second user
    
    print("\n8. Testing thread cleanup edge cases...")
    # Delete all but one reply
    for reply in replies[:-1] + more_replies:
        response = await client.delete(
            f"/api/messages/{reply.message_id}",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 200
    
    # Verify thread still exists with remaining replies
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"parent_id": parent_data.message_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    thread_messages = [MessageResponse(**msg) for msg in response.json()]
    assert len(thread_messages) == 2  # Last original reply + second user's reply
    
    # Delete last replies
    response = await client.delete(
        f"/api/messages/{replies[-1].message_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    
    # Delete second user's reply (should trigger full thread cleanup)
    response = await client.delete(
        f"/api/messages/{thread_messages[0].message_id}",
        headers={"Authorization": f"Bearer {second_user_token['access_token']}"}
    )
    assert response.status_code == 200
    
    # Verify thread is completely gone
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"parent_id": parent_data.message_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 404

async def test_message_permissions(
    client: AsyncClient,
    access_token: str,
    second_user_token: Dict[str, Any]
) -> None:
    """Test message permissions across different channel types"""
    print("\n1. Testing public channel permissions...")
    # Create public channel
    public_channel_create = ChannelCreate(
        name="test-public-msg",
        type="public"
    )
    response = await client.post(
        "/api/channels",
        json=public_channel_create.model_dump(),
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    public_channel = ChannelResponse(**response.json())
    
    # Try to post message as non-member (should fail)
    message_create = MessageCreate(content="Unauthorized message", channel_id=public_channel.channel_id)
    response = await client.post(
        "/api/messages",
        json=message_create.model_dump(),
        headers={"Authorization": f"Bearer {second_user_token['access_token']}"}
    )
    assert response.status_code == 403
    
    print("\n2. Testing private channel permissions...")
    # Create private channel
    private_channel_create = ChannelCreate(
        name="test-private-msg",
        type="private"
    )
    response = await client.post(
        "/api/channels",
        json=private_channel_create.model_dump(),
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    private_channel = ChannelResponse(**response.json())
    
    # Try to read messages as non-member (should fail)
    response = await client.get(
        f"/api/messages/channels/{private_channel.channel_id}",
        headers={"Authorization": f"Bearer {second_user_token['access_token']}"}
    )
    assert response.status_code == 403

if __name__ == "__main__":
    pytest.main([__file__]) 