from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import Response
from ...core.auth import get_current_user
from ...core.database import get_db
from ...schemas.message import MessageCreate, MessageResponse, MessageUpdate, MessageWithAttachments
from ...services.message_service import message_service
from ...services.attachment_service import attachment_service
from ...utils import debug_log

import aiosqlite
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/messages", tags=["messages"])

@router.post("", response_model=MessageResponse, status_code=201)
async def create_message(
    message: MessageCreate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db)
):
    """Create a new message. Can be sent to either:
    1. An existing channel (using channel_id)
    2. A user (using recipient_id) - will create/get DM channel
    """
    try:
        if message.channel_id is not None:
            # Regular channel message
            message_id = await message_service.create_message(
                db=db,
                channel_id=message.channel_id,
                user_id=current_user["user_id"],
                content=message.content,
                parent_id=message.parent_id
            )
        else:
            # DM or Notes message
            message_id = await message_service.create_message(
                db=db,
                channel_id=None,
                user_id=current_user["user_id"],
                content=message.content,
                parent_id=message.parent_id,
                other_user_id=message.recipient_id
            )
        
        message_data = await message_service.get_message(
            db=db,
            message_id=message_id,
            user_id=current_user["user_id"]
        )
        
        return MessageResponse(
            message_id=message_data["message_id"],
            channel_id=message_data["channel_id"],
            user_id=message_data["user_id"],
            content=message_data["content"],
            created_at=message_data["created_at"],
            edited_at=message_data["updated_at"],
            display_name=message_data["display_name"],
            parent_id=message_data["parent_id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/channels/{channel_id}", response_model=List[MessageWithAttachments])
async def list_messages(
    channel_id: int,
    before: Optional[int] = Query(None, description="Get messages before this message_id"),
    limit: int = Query(50, le=100),
    parent_id: Optional[int] = Query(None, description="Get messages in a specific thread"),
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db)
):
    """List messages in a channel with pagination"""
    try:
        messages = await message_service.list_messages(
            db=db,
            channel_id=channel_id,
            user_id=current_user["user_id"],
            before=before,
            limit=limit,
            parent_id=parent_id
        )
        
        # Get attachments for messages
        result = []
        for msg in messages:
            attachments = await attachment_service.get_message_attachments(
                db=db,
                message_id=msg["message_id"]
            )
            
            result.append(MessageWithAttachments(
                message_id=msg["message_id"],
                channel_id=msg["channel_id"],
                user_id=msg["user_id"],
                content=msg["content"],
                created_at=msg["created_at"],
                edited_at=msg["updated_at"],
                display_name=msg["display_name"],
                parent_id=msg["parent_id"],
                attachments=attachments
            ))
        
        return result
    except ValueError as e:
        if str(e) == "Parent message not found":
            raise HTTPException(status_code=404, detail="Thread not found")
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{message_id}", response_model=MessageResponse)
async def update_message(
    message_id: int,
    message: MessageUpdate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db)
):
    """Update a message"""
    try:
        message_data = await message_service.update_message(
            db=db,
            message_id=message_id,
            user_id=current_user["user_id"],
            content=message.content
        )
        
        return MessageResponse(
            message_id=message_data["message_id"],
            channel_id=message_data["channel_id"],
            user_id=message_data["user_id"],
            content=message_data["content"],
            created_at=message_data["created_at"],
            edited_at=message_data["updated_at"],
            display_name=message_data["display_name"],
            parent_id=message_data["parent_id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{message_id}")
async def delete_message(
    message_id: int,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db)
):
    """Delete a message"""
    try:
        await message_service.delete_message(
            db=db,
            message_id=message_id,
            user_id=current_user["user_id"]
        )
        return Response(status_code=204)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) 