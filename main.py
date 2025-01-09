from fastapi import FastAPI
from app.api.routes import auth, channels, messages, reactions
from app.core.database import init_db
import asyncio

app = FastAPI()

# Include routers with /api prefix
api_app = FastAPI(prefix="/api")
api_app.include_router(auth.router)
api_app.include_router(channels.router)
api_app.include_router(messages.router)
api_app.include_router(reactions.router)

app.mount("/api", api_app)

@app.get("/")
async def root():
    return {"message": "Welcome to Yotsu Chat!"}

@app.on_event("startup")
async def startup_event():
    await init_db()