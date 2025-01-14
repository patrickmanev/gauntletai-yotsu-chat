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
    assert response.status_code == 204
    
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
    """
    Test comprehensive thread operations, ensuring:
    1) Thread creation,
    2) Replies,
    3) Visibility in main channel view,
    4) Thread checks (no nested replies),
    5) Permissions (other users can join/reply),
    6) Soft-deletion of parent message,
    7) Thread cleanup edge cases,
    8) Additional checks while second user is present,
    9) Ownership/role checks,
    10) Final cascade deletion,
    11) Confirming no stale data remains,
    12) etc.
    """

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

    print("\n3. Testing thread visibility in main channel view...")
    # Verify that the main channel view retrieves top-level messages plus child replies (unpaged).
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    channel_messages = [MessageResponse(**msg) for msg in response.json()]

    # Should see 1 top-level (the parent) + 3 child replies
    assert len(channel_messages) == 4, f"Expected 4 total (1 parent + 3 replies), got {len(channel_messages)}"
    parent_in_channel = next((m for m in channel_messages if m.message_id == parent_data.message_id), None)
    assert parent_in_channel, "Parent message must appear in the main channel listing"
    children_of_parent = [m for m in channel_messages if m.parent_id == parent_data.message_id]
    assert len(children_of_parent) == 3, "Should have 3 replies in main channel view"

    print("\n4. Testing thread-specific view (parent_id in query) before adding more replies...")
    # If we specifically request the thread via parent_id, only that thread's existing replies should appear
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"parent_id": parent_data.message_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    thread_only_msgs = [MessageResponse(**msg) for msg in response.json()]
    assert len(thread_only_msgs) == 3, (
        f"Expected exactly the 3 replies for that thread, got {len(thread_only_msgs)}"
    )
    assert all(m.parent_id == parent_data.message_id for m in thread_only_msgs)

    print("\n5. Testing thread pagination for main channel view...")
    # Create more replies for pagination testing
    more_replies: List[MessageResponse] = []
    for i in range(7):  # This pushes total replies to 10
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

    # Verify the parent thread now has 10 replies (all unpaged in thread view)
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"parent_id": parent_data.message_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    thread_messages = [MessageResponse(**msg) for msg in response.json()]
    assert len(thread_messages) == 10, "Thread view should show all replies"
    assert all(msg.parent_id == parent_data.message_id for msg in thread_messages)

    # Test channel-level view with a limit
    # Because we have only 1 top-level message at this point, that single top-level plus its 10 replies
    # are grouped together, for a total of 11 messages.
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"limit": 5},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    first_page = [MessageResponse(**msg) for msg in response.json()]

    top_level_msgs_in_first_page = [m for m in first_page if m.parent_id is None]
    assert len(top_level_msgs_in_first_page) == 1, (
        "Expected exactly 1 top-level (the parent) in this page."
    )
    assert len(first_page) == 11, (
        "Parent message plus 10 replies = 11 total."
    )

    print("\n6. Testing next page of top-level messages (should be empty in this scenario)...")
    # We only have 1 top-level so far; there's nothing older than that
    min_top_level_id = min(m.message_id for m in top_level_msgs_in_first_page)
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"limit": 5, "before": min_top_level_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    second_page = [MessageResponse(**msg) for msg in response.json()]
    assert len(second_page) == 0, "No older top-level messages should exist yet."

    print("\n7. Adding additional top-level messages for more pagination tests...")
    new_parents: List[MessageResponse] = []
    for i in range(3):
        top_msg = MessageCreate(content=f"Another top-level {i+1}", channel_id=channel_id)
        tm_resp = await client.post(
            "/api/messages",
            json=top_msg.model_dump(),
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert tm_resp.status_code == 201
        new_parents.append(MessageResponse(**tm_resp.json()))

    # Fetch with limit=2
    list_resp_1 = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"limit": 2},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert list_resp_1.status_code == 200
    top_levels_in_slice = [MessageResponse(**msg) for msg in list_resp_1.json()]
    assert len(top_levels_in_slice) == 2, f"Expected 2 new top-level messages, got {len(top_levels_in_slice)}"

    # Next page with 'before' param => should see the older parent + its 10 replies
    min_top_level_id = min(m.message_id for m in top_levels_in_slice)
    response = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"limit": 2, "before": min_top_level_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    second_slice = [MessageResponse(**msg) for msg in response.json()]

    top_levels_in_second_slice = [m for m in second_slice if m.parent_id is None]
    assert len(top_levels_in_second_slice) == 1, "There was only 1 older top-level (the original parent)."
    assert len(second_slice) == 11, (
        "One top-level with 10 replies => 11 total in the second slice."
    )

    print("\n8. Testing nested reply prevention...")
    nested_message = MessageCreate(
        content="Nested reply attempt",
        channel_id=channel_id,
        parent_id=replies[0].message_id  # This is itself a reply
    )
    nested_response = await client.post(
        "/api/messages",
        json=nested_message.model_dump(),
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert nested_response.status_code == 400, "Should reject nested replies"
    assert "Cannot reply to a reply" in nested_response.json()["detail"]

    print("\n9. Testing multi-user thread access...")
    add_member_resp = await client.post(
        f"/api/members/{channel_id}",
        json={"user_id": second_user_token["user_id"]},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert add_member_resp.status_code == 201

    second_user_reply = MessageCreate(
        content="Reply from second user",
        channel_id=channel_id,
        parent_id=parent_data.message_id
    )
    su_resp = await client.post(
        "/api/messages",
        json=second_user_reply.model_dump(),
        headers={"Authorization": f"Bearer {second_user_token['access_token']}"}
    )
    assert su_resp.status_code == 201
    second_user_reply_data = MessageResponse(**su_resp.json())

    print("\n10. Testing thread parent deletion (soft-delete)...")
    delete_parent_resp = await client.delete(
        f"/api/messages/{parent_data.message_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert delete_parent_resp.status_code == 204

    # Replies remain visible
    thread_view = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"parent_id": parent_data.message_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert thread_view.status_code == 200
    thread_data = [MessageResponse(**msg) for msg in thread_view.json()]
    # 10 original + 1 from second user = 11
    assert len(thread_data) == 11, "All replies remain after parent soft-delete"

    print("\n11. Testing partial cleanup of replies...")
    # We'll keep the last element of 'replies'; remove everything else
    for rep in replies[:-1] + more_replies:
        dresp = await client.delete(
            f"/api/messages/{rep.message_id}",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert dresp.status_code == 204

    updated_thread_view = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"parent_id": parent_data.message_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert updated_thread_view.status_code == 200
    updated_thread_data = [MessageResponse(**msg) for msg in updated_thread_view.json()]
    # leftover + second user's => 2
    assert len(updated_thread_data) == 2, f"Expected 2 replies left, got {len(updated_thread_data)}"

    print("\n12. Testing final thread cleanup scenario (removing last replies)...")
    leftover_reply_id = replies[-1].message_id
    leftover_del_resp = await client.delete(
        f"/api/messages/{leftover_reply_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert leftover_del_resp.status_code == 204

    # Remove second user's reply
    leftover_thread_view = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"parent_id": parent_data.message_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert leftover_thread_view.status_code == 200
    leftover_data = [MessageResponse(**msg) for msg in leftover_thread_view.json()]
    assert len(leftover_data) == 1, f"Expected 1 left, found {len(leftover_data)}"

    final_del_resp = await client.delete(
        f"/api/messages/{second_user_reply_data.message_id}",
        headers={"Authorization": f"Bearer {second_user_token['access_token']}"}
    )
    assert final_del_resp.status_code == 204

    print("\n13. Verifying thread is completely gone after final reply deletion...")
    final_thread_check = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"parent_id": parent_data.message_id},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    # This test expects 404 after complete removal
    assert final_thread_check.status_code == 404, (
        "Expected 404 since parent is soft-deleted and all replies are gone"
    )

    print("\n14. Creating more top-level messages to confirm channel pagination in final cleanup state...")
    newer_parents = []
    for i in range(3):
        top_msg = MessageCreate(content=f"Fresh top-level {i+1}", channel_id=channel_id)
        tm_resp = await client.post(
            "/api/messages",
            json=top_msg.model_dump(),
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert tm_resp.status_code == 201
        newer_parents.append(MessageResponse(**tm_resp.json()))

    list_resp_1 = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"limit": 2},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert list_resp_1.status_code == 200
    first_slice = [MessageResponse(**msg) for msg in list_resp_1.json()]
    assert len(first_slice) == 2, f"Expected 2 top-level messages, got {len(first_slice)}"

    print("\n15. Confirming 'before' param for next page of top-level messages (3rd new message)...")
    min_id_in_page = min(m.message_id for m in first_slice)
    list_resp_2 = await client.get(
        f"/api/messages/channels/{channel_id}",
        params={"limit": 2, "before": min_id_in_page},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert list_resp_2.status_code == 200
    second_slice = [MessageResponse(**msg) for msg in list_resp_2.json()]
    assert len(second_slice) >= 1, "Expected at least 1 more top-level message"

    print("\n> test_thread_operations completed successfully!")

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