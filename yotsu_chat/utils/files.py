"""File handling utilities for secure file uploads and management."""

import os
import hashlib
# import magic
from typing import Set, Dict, Any
from fastapi import UploadFile
from .errors import raise_invalid_file, raise_file_too_large

# Configuration for file upload constraints and security
MAX_FILE_SIZE: int = 20 * 1024 * 1024  # 20MB
UPLOAD_DIR: str = "uploads"

# Allowed file extensions and their corresponding MIME types
ALLOWED_EXTENSIONS: Set[str] = {
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    # Documents
    ".pdf", ".doc", ".docx", ".txt", ".md",
    # Audio
    ".mp3", ".wav", ".m4a",
    # Video
    ".mp4", ".webm",
    # Archives
    ".zip", ".rar", ".7z",
    # Code
    ".py", ".js", ".html", ".css", ".json"
}

async def save_upload_file(file: UploadFile, message_id: int) -> Dict[str, Any]:
    """
    Save an uploaded file with security checks.
    Returns file metadata for database storage.
    """
    # Create uploads directory if it doesn't exist
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    # Read file content
    content = await file.read(MAX_FILE_SIZE)
    
    # Check file size
    if len(content) > MAX_FILE_SIZE:
        raise_file_too_large(details={"max_size": MAX_FILE_SIZE})
    
    # Get file extension and check if it's allowed
    if not file.filename:
        raise_invalid_file("No filename provided")
    
    filename: str = str(file.filename)  # Ensure we have a string
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise_invalid_file(f"File extension {file_ext} not allowed")
    
    # MIME type checking temporarily disabled until file sharing implementation
    # mime_type = magic.from_buffer(content, mime=True)
    mime_type = "application/octet-stream"  # Default MIME type for now
    
    # Calculate file hash
    file_hash = hashlib.sha256(content).hexdigest()
    
    # Create a safe filename
    safe_filename = f"{message_id}_{file_hash[:8]}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    
    # Save the file
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Return file metadata
    return {
        "filename": safe_filename,
        "original_filename": file.filename,
        "file_type": file_ext[1:],  # Remove the dot
        "size": len(content),
        "mime_type": mime_type,
        "file_hash": file_hash
    }

def delete_file(filename: str) -> bool:
    """Delete a file from the uploads directory"""
    try:
        file_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
    except Exception:
        pass
    return False 