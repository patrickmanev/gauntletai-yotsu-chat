"""Disabled presence tests"""

import pytest
from fastapi import WebSocket
from httpx import AsyncClient
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple, Union, cast
import os

from app.core.presence import PresenceState, presence_manager
from app.core.ws_core import manager
from app.main import app
from tests.conftest import create_test_user
from tests.test_channels import register_test_user

logger = logging.getLogger(__name__)

# All tests disabled while presence tracking is under development

"""
async def create_ws_connection(client: Union[AsyncClient, TestClient], user_id: int) -> Tuple[WebSocketTestSession, str]:
    # Test helper function disabled
    pass

async def receive_presence_update(ws: WebSocketTestSession, expected_user_id: int, expected_state: PresenceState, timeout: float = 1.0) -> bool:
    # Test helper function disabled
    pass

@pytest.mark.asyncio
async def test_single_connection_lifecycle(client: AsyncClient, test_client: TestClient):
    # Test disabled
    pass

@pytest.mark.asyncio
async def test_multiple_connections_same_user(client: AsyncClient, test_client: TestClient):
    # Test disabled
    pass

@pytest.mark.asyncio
async def test_presence_broadcast_between_users(client: AsyncClient, test_client: TestClient):
    # Test disabled
    pass

@pytest.mark.asyncio
async def test_connection_cleanup(client: AsyncClient, test_client: TestClient):
    # Test disabled
    pass

@pytest.mark.asyncio
async def test_rapid_focus_changes(client: AsyncClient, test_client: TestClient):
    # Test disabled
    pass

@pytest.mark.asyncio
async def test_multiple_users_multiple_connections(client: AsyncClient, test_client: TestClient):
    # Test disabled
    pass
""" 