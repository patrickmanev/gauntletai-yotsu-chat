import pytest
from httpx import AsyncClient
from typing import Dict, Any

pytestmark = pytest.mark.asyncio

@pytest.mark.asyncio
async def test_message_operations(
    client: AsyncClient,
    access_token: str,
    second_user_token: Dict[str, Any],
    test_channel: Dict[str, Any]
):
    """Test basic message operations and permissions"""
    channel_id = test_channel["channel_id"]
    
    # Add second user to the channel
    response = await client.post(
        f"/api/channels/{channel_id}/members",
        json={"user_id": second_user_token["user_id"], "role": "member"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    
    # Create a message
    response = await client.post(
        f"/api/messages/channels/{channel_id}",
        json={"content": "Test message"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    message_data = response.json()
    
    # Get messages
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    messages = response.json()
    assert len(messages) == 1
    assert messages[0]["message_id"] == message_data["message_id"]
    
    # Update message
    response = await client.put(
        f"/api/messages/{message_data['message_id']}",
        json={"content": "Updated message"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    updated_message = response.json()
    assert updated_message["content"] == "Updated message"
    
    # Try to update message as another user (should fail)
    response = await client.put(
        f"/api/messages/{message_data['message_id']}",
        json={"content": "Unauthorized update"},
        headers={"Authorization": f"Bearer {second_user_token['access_token']}"}
    )
    assert response.status_code == 403
    
    # Delete message
    response = await client.delete(
        f"/api/messages/{message_data['message_id']}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200

async def test_create_message_in_thread(client: AsyncClient, access_token: str, test_channel: Dict[str, Any]):
    """Test creating messages in a thread"""
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
    assert reply_data["parent_id"] == parent_data["message_id"]
    
    # Get messages in thread
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"parent_id": parent_data["message_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    thread_messages = response.json()
    assert len(thread_messages) == 1
    assert thread_messages[0]["message_id"] == reply_data["message_id"]

async def test_thread_message_validation(client: AsyncClient, access_token: str, test_channel: Dict[str, Any]):
    """Test thread message validation"""
    channel_id = test_channel["channel_id"]
    
    # Try to create a reply to non-existent message
    invalid_response = await client.post(
        f"/api/messages/channels/{channel_id}",
        json={
            "content": "Invalid reply",
            "parent_id": 99999
        },
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert invalid_response.status_code == 404
    assert "Parent message not found" in invalid_response.json()["detail"]
    
    # Create parent message
    parent_response = await client.post(
        f"/api/messages/channels/{channel_id}",
        json={"content": "Parent message"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert parent_response.status_code == 201
    parent_data = parent_response.json()
    
    # Try to create a reply to a reply (should fail)
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
    
    nested_response = await client.post(
        f"/api/messages/channels/{channel_id}",
        json={
            "content": "Nested reply",
            "parent_id": reply_data["message_id"]
        },
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert nested_response.status_code == 400
    assert "Cannot reply to a reply" in nested_response.json()["detail"]

async def test_delete_thread_parent(client: AsyncClient, access_token: str, thread_with_reply: Dict[str, Any]):
    """Test deleting a parent message in a thread"""
    parent_data = thread_with_reply["parent"]
    
    # Delete parent message
    delete_response = await client.delete(
        f"/api/messages/{parent_data['message_id']}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert delete_response.status_code == 200
    
    # Get messages in thread
    response = await client.get(
        f"/api/messages/channels/{parent_data['channel_id']}",
        params={"parent_id": parent_data["message_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    thread_messages = response.json()
    assert len(thread_messages) == 1  # Reply should still be visible
    assert thread_messages[0]["parent_id"] == parent_data["message_id"]

async def test_delete_thread_parent_with_replies(client: AsyncClient, access_token: str, thread_with_reply: Dict[str, Any]):
    """Test deleting a thread parent message that has replies"""
    parent_data = thread_with_reply["parent"]
    
    # Delete parent message
    delete_response = await client.delete(
        f"/api/messages/{parent_data['message_id']}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert delete_response.status_code == 200
    
    # Get messages in thread
    response = await client.get(
        f"/api/messages/channels/{parent_data['channel_id']}",
        params={"parent_id": parent_data["message_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    thread_messages = response.json()
    assert len(thread_messages) == 1  # Reply should still be visible
    assert thread_messages[0]["parent_id"] == parent_data["message_id"]

async def test_delete_last_reply_deletes_deleted_parent(client: AsyncClient, access_token: str, thread_with_reply: Dict[str, Any]):
    """Test that deleting the last reply of a deleted parent message also deletes the parent"""
    parent_data = thread_with_reply["parent"]
    reply_data = thread_with_reply["reply"]
    
    # Delete parent message first (should be marked as deleted)
    await client.delete(
        f"/api/messages/{parent_data['message_id']}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    # Delete the reply
    delete_response = await client.delete(
        f"/api/messages/{reply_data['message_id']}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert delete_response.status_code == 200
    
    # Try to get messages in thread (should return empty)
    response = await client.get(
        f"/api/messages/channels/{parent_data['channel_id']}",
        params={"parent_id": parent_data["message_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 404  # Parent should be fully deleted

async def test_delete_reply_keeps_deleted_parent_if_other_replies_exist(
    client: AsyncClient, access_token: str, thread_with_reply: Dict[str, Any]
):
    """Test that deleting a reply keeps the deleted parent if other replies exist"""
    
    parent_data = thread_with_reply["parent"]
    reply1_data = thread_with_reply["reply"]
    
    # Create another reply
    reply2_response = await client.post(
        f"/api/messages/channels/{parent_data['channel_id']}",
        json={
            "content": "Reply 2",
            "parent_id": parent_data["message_id"]
        },
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert reply2_response.status_code == 201
    reply2_data = reply2_response.json()
    
    # Delete parent message (should be marked as deleted)
    await client.delete(
        f"/api/messages/{parent_data['message_id']}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    # Delete first reply
    delete_response = await client.delete(
        f"/api/messages/{reply1_data['message_id']}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert delete_response.status_code == 200
    
    # Get messages in thread (should still show second reply)
    response = await client.get(
        f"/api/messages/channels/{parent_data['channel_id']}",
        params={"parent_id": parent_data["message_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    thread_messages = response.json()
    assert len(thread_messages) == 1
    assert thread_messages[0]["message_id"] == reply2_data["message_id"] 