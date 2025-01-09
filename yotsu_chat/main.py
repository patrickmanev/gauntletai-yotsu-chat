from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from yotsu_chat.core.database import init_db
from yotsu_chat.api.routes import auth, channels, messages, reactions, websocket
import os

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api")
app.include_router(channels.router, prefix="/api")
app.include_router(messages.router, prefix="/api")
app.include_router(reactions.router, prefix="/api")
app.include_router(websocket.router)  # WebSocket router doesn't need prefix

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    # Always create tables, but only drop them in test mode
    await init_db()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"} 