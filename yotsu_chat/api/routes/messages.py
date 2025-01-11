from fastapi import APIRouter, Depends, HTTPException, Query
from ...core.auth import get_current_user
from ...core.database import get_db
from ...schemas.message import MessageCreate, MessageUpdate, MessageResponse, MessageWithAttachments
from ...utils.errors import raise_unauthorized
from ...core.ws_core import manager as ws_manager
import json

router = APIRouter(prefix="/messages", tags=["messages"])

@router.post("/channels/{channel_id}", response_model=MessageResponse, status_code=201)
async def create_message(
    channel_id: int,
    message: MessageCreate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db)
):
    """Create a new message in a channel"""
    # If this is a reply, verify the parent message exists and is in the same channel
    parent = None
    if message.parent_id:
        async with db.execute(
            "SELECT channel_id, parent_id, thread_id FROM messages WHERE message_id = ?",
            (message.parent_id,)
        ) as cursor:
            parent = await cursor.fetchone()
            if not parent:
                raise HTTPException(status_code=404, detail="Parent message not found")
            if parent["channel_id"] != channel_id:
                raise HTTPException(status_code=400, detail="Parent message must be in the same channel")
            if parent["parent_id"] is not None:
                raise HTTPException(status_code=400, detail="Cannot reply to a reply")
    
    try:
        # Check if user is member of channel
        async with db.execute(
            "SELECT 1 FROM channels_members WHERE channel_id = ? AND user_id = ?",
            (channel_id, current_user["user_id"])
        ) as cursor:
            if not await cursor.fetchone():
                raise_unauthorized("You are not a member of this channel")
        
        # Create message (without thread_id initially)
        async with db.execute(
            """
            INSERT INTO messages (channel_id, user_id, content, parent_id)
            VALUES (?, ?, ?, ?)
            RETURNING message_id
            """,
            (channel_id, current_user["user_id"], message.content, message.parent_id)
        ) as cursor:
            message_id = (await cursor.fetchone())[0]
        
        # If this is a reply, update the thread_id
        if message.parent_id:
            thread_id = parent["thread_id"] if parent["thread_id"] else message.parent_id
            await db.execute(
                """
                UPDATE messages
                SET thread_id = ?
                WHERE message_id = ?
                """,
                (thread_id, message_id)
            )
        
        # Get message details for response
        async with db.execute(
            """
            SELECT m.*, u.display_name
            FROM messages m
            JOIN users u ON m.user_id = u.user_id
            WHERE m.message_id = ?
            """,
            (message_id,)
        ) as cursor:
            message_data = await cursor.fetchone()
            if not message_data:
                raise HTTPException(status_code=500, detail="Failed to retrieve created message")
            
            response = MessageResponse(
                message_id=message_data["message_id"],
                channel_id=message_data["channel_id"],
                user_id=message_data["user_id"],
                content=message_data["content"],
                created_at=message_data["created_at"],
                edited_at=message_data["updated_at"],
                display_name=message_data["display_name"],
                parent_id=message_data["parent_id"]
            )
        
        await db.commit()
        
        # Broadcast message creation to channel
        event = {
            "type": "message.created",
            "data": {
                "message_id": message_id,
                "channel_id": channel_id,
                "content": message.content,
                "user_id": current_user["user_id"],
                "parent_id": message.parent_id,
                "created_at": response.created_at.isoformat()
            }
        }
        await ws_manager.broadcast_to_channel(channel_id, event)
        
        return response
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/channels/{channel_id}", response_model=list[MessageWithAttachments])
async def list_messages(
    channel_id: int,
    before: int = Query(None, description="Get messages before this message_id"),
    limit: int = Query(50, le=100),
    parent_id: int = Query(None, description="Get messages in a specific thread"),
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db)
):
    """List messages in a channel with pagination"""
    async with db.cursor() as cur:
        # Check if user has access to channel
        await cur.execute("""
            SELECT type FROM channels WHERE channel_id = ?
        """, (channel_id,))
        
        channel = await cur.fetchone()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
            
        if channel["type"] == "private":
            await cur.execute("""
                SELECT 1 FROM channels_members
                WHERE channel_id = ? AND user_id = ?
            """, (channel_id, current_user["user_id"]))
            if not await cur.fetchone():
                raise_unauthorized("You don't have access to this channel")
        
        # Get messages
        query = """
            SELECT m.*, u.display_name
            FROM messages m
            JOIN users u ON m.user_id = u.user_id
            WHERE m.channel_id = ?
        """
        params = [channel_id]
        
        # Filter by thread if specified
        if parent_id is not None:
            # Check if parent exists
            await cur.execute("""
                SELECT 1 FROM messages 
                WHERE message_id = ? AND channel_id = ?
            """, (parent_id, channel_id))
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="Parent message not found")
            
            query += " AND m.parent_id = ?"
            params.append(parent_id)
        else:
            query += " AND m.parent_id IS NULL"  # Only get top-level messages
        
        if before:
            query += " AND m.message_id < ?"
            params.append(before)
        
        query += " ORDER BY m.message_id DESC LIMIT ?"
        params.append(limit)
        
        await cur.execute(query, params)
        messages = await cur.fetchall()
        
        # Get attachments for messages
        result = []
        for msg in messages:
            await cur.execute("""
                SELECT *
                FROM attachments
                WHERE message_id = ?
                ORDER BY created_at
            """, (msg["message_id"],))
            
            attachments = await cur.fetchall()
            result.append(MessageWithAttachments(
                message_id=msg["message_id"],
                channel_id=msg["channel_id"],
                user_id=msg["user_id"],
                content=msg["content"],
                created_at=msg["created_at"],
                edited_at=msg["updated_at"],
                display_name=msg["display_name"],
                parent_id=msg["parent_id"],
                attachments=list(attachments)
            ))
        
        return result

@router.put("/{message_id}", response_model=MessageResponse)
async def update_message(
    message_id: int,
    message: MessageUpdate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db)
):
    """Update a message"""
    async with db.cursor() as cur:
        # Check if message exists and user is the author
        await cur.execute("""
            SELECT m.*, u.display_name
            FROM messages m
            JOIN users u ON m.user_id = u.user_id
            WHERE m.message_id = ?
        """, (message_id,))
        
        msg = await cur.fetchone()
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")
        
        if msg["user_id"] != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="You can only edit your own messages")
        
        # Update message
        await cur.execute("""
            UPDATE messages
            SET content = ?, updated_at = CURRENT_TIMESTAMP
            WHERE message_id = ?
        """, (message.content, message_id))
        
        await db.commit()
        
        # Get updated message
        await cur.execute("""
            SELECT m.*, u.display_name
            FROM messages m
            JOIN users u ON m.user_id = u.user_id
            WHERE m.message_id = ?
        """, (message_id,))
        
        updated = await cur.fetchone()
        response = MessageResponse(
            message_id=updated["message_id"],
            channel_id=updated["channel_id"],
            user_id=updated["user_id"],
            content=updated["content"],
            created_at=updated["created_at"],
            edited_at=updated["updated_at"],
            display_name=updated["display_name"],
            parent_id=updated["parent_id"]
        )
        
        # Broadcast message update to channel
        event = {
            "type": "message.updated",
            "data": {
                "message_id": message_id,
                "channel_id": updated["channel_id"],
                "content": message.content,
                "user_id": current_user["user_id"],
                "updated_at": response.edited_at.isoformat()
            }
        }
        await ws_manager.broadcast_to_channel(updated["channel_id"], event)
        
        return response

@router.delete("/{message_id}")
async def delete_message(
    message_id: int,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db)
):
    """Delete a message"""
    async with db.cursor() as cur:
        # Check if message exists and user is the author
        await cur.execute("""
            SELECT user_id, channel_id, parent_id, content
            FROM messages
            WHERE message_id = ?
        """, (message_id,))
        
        msg = await cur.fetchone()
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")
        
        # Check if user is author or channel admin/owner
        if msg["user_id"] != current_user["user_id"]:
            await cur.execute("""
                SELECT role FROM channels_members
                WHERE channel_id = ? AND user_id = ?
            """, (msg["channel_id"], current_user["user_id"]))
            
            member = await cur.fetchone()
            if not member or member["role"] not in ["owner", "admin"]:
                raise HTTPException(status_code=403, detail="You don't have permission to delete this message")
        
        # Check if this is a thread parent message (no parent_id and has replies)
        if msg["parent_id"] is None:
            await cur.execute("""
                SELECT EXISTS(
                    SELECT 1 
                    FROM messages 
                    WHERE parent_id = ?
                ) as has_replies
            """, (message_id,))
            
            has_replies = (await cur.fetchone())["has_replies"]
            
            if has_replies:
                # This is a thread parent with replies - update content instead of deleting
                await cur.execute("""
                    UPDATE messages 
                    SET content = 'This message was deleted',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE message_id = ?
                """, (message_id,))
                
                # Delete all reactions for this message
                await cur.execute("DELETE FROM reactions WHERE message_id = ?", (message_id,))
                
                await db.commit()
                
                # Broadcast message soft delete to channel
                event = {
                    "type": "message.soft_deleted",
                    "data": {
                        "message_id": message_id,
                        "channel_id": msg["channel_id"]
                    }
                }
                await ws_manager.broadcast_to_channel(msg["channel_id"], event)
                
                return {"message": "Message marked as deleted"}
        
        # For regular messages, thread replies, or thread parents with no replies:
        # If this is a reply and the parent message is already "deleted", check if this is the last existing reply
        if msg["parent_id"]:
            await cur.execute("""
                SELECT content, message_id 
                FROM messages 
                WHERE message_id = ? AND content = 'This message was deleted'
            """, (msg["parent_id"],))
            
            parent = await cur.fetchone()
            if parent:
                # Check if there will be any remaining replies after this deletion
                await cur.execute("""
                    SELECT EXISTS(
                        SELECT 1
                        FROM messages 
                        WHERE parent_id = ? AND message_id != ?
                    ) as has_other_replies
                """, (msg["parent_id"], message_id))
                
                has_other_replies = (await cur.fetchone())["has_other_replies"]
                if not has_other_replies:
                    # First delete all reactions and attachments for all replies
                    await cur.execute("""
                        DELETE FROM reactions WHERE message_id IN (
                            SELECT message_id FROM messages WHERE parent_id = ?
                        )
                    """, (msg["parent_id"],))
                    await cur.execute("""
                        DELETE FROM attachments WHERE message_id IN (
                            SELECT message_id FROM messages WHERE parent_id = ?
                        )
                    """, (msg["parent_id"],))
                    # Then delete all replies
                    await cur.execute("DELETE FROM messages WHERE parent_id = ?", (msg["parent_id"],))
                    
                    # Now delete reactions and attachments for the parent
                    await cur.execute("DELETE FROM reactions WHERE message_id = ?", (msg["parent_id"],))
                    await cur.execute("DELETE FROM attachments WHERE message_id = ?", (msg["parent_id"],))
                    # Finally delete the parent message
                    await cur.execute("DELETE FROM messages WHERE message_id = ?", (msg["parent_id"],))
                    
                    # Broadcast parent message hard delete to channel
                    event = {
                        "type": "message.deleted",
                        "data": {
                            "message_id": msg["parent_id"],
                            "channel_id": msg["channel_id"]
                        }
                    }
                    await ws_manager.broadcast_to_channel(msg["channel_id"], event)
        
        # Delete any reactions for this message
        await cur.execute("DELETE FROM reactions WHERE message_id = ?", (message_id,))
        # Delete any attachments for this message
        await cur.execute("DELETE FROM attachments WHERE message_id = ?", (message_id,))
        # Finally delete the message itself
        await cur.execute("DELETE FROM messages WHERE message_id = ?", (message_id,))
        await db.commit()
        
        # Broadcast message hard delete to channel
        event = {
            "type": "message.deleted",
            "data": {
                "message_id": message_id,
                "channel_id": msg["channel_id"]
            }
        }
        await ws_manager.broadcast_to_channel(msg["channel_id"], event)
        
        return {"message": "Message deleted successfully"} 