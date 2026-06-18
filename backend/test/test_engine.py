import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from engine import GameEngine
from manager import GameManager


@pytest.fixture
def mock_bot():
    """Mock Discord Bot"""
    return MagicMock()


@pytest.fixture
def mock_sio():
    """Mock Socket.IO Server"""
    return AsyncMock()


@pytest.fixture
def game_engine(mock_bot, mock_sio):
    """Create GameEngine instance with mocked dependencies"""
    return GameEngine(mock_bot, mock_sio)


@pytest.mark.asyncio
async def test_on_web_client_connect_default_scene(game_engine):
    """Test web client connect with default scene"""
    # Arrange
    test_sid = "test_session_123"
    
    # Act
    await game_engine.on_web_client_connect(test_sid)
    
    # Assert
    game_engine.sio.emit.assert_called_once_with(
        'scene_update',
        {
            "name": "未开始",
            "description": "已连接服务器"
        },
        room=test_sid
    )


@pytest.mark.asyncio
async def test_on_web_client_connect_custom_scene(game_engine):
    """Test web client connect with custom scene"""
    # Arrange
    test_sid = "test_session_456"
    game_engine.room_state["scene"] = "废弃古堡"
    
    # Act
    await game_engine.on_web_client_connect(test_sid)
    
    # Assert
    game_engine.sio.emit.assert_called_once_with(
        'scene_update',
        {
            "name": "废弃古堡",
            "description": "已连接服务器"
        },
        room=test_sid
    )


@pytest.mark.asyncio
async def test_on_web_client_connect_empty_scene(game_engine):
    """Test web client connect when scene is empty"""
    # Arrange
    test_sid = "test_session_789"
    game_engine.room_state = {}
    
    # Act
    await game_engine.on_web_client_connect(test_sid)
    
    # Assert
    game_engine.sio.emit.assert_called_once_with(
        'scene_update',
        {
            "name": "等待中",
            "description": "已连接服务器"
        },
        room=test_sid
    )


@pytest.mark.asyncio
async def test_on_web_client_connect_sio_exception(game_engine):
    """Test web client connect when Socket.IO emit fails"""
    # Arrange
    test_sid = "test_session_error"
    game_engine.sio.emit.side_effect = Exception("Connection failed")
    
    # Act & Assert
    with pytest.raises(Exception, match="Connection failed"):
        await game_engine.on_web_client_connect(test_sid)


@pytest.mark.asyncio
async def test_on_web_client_connect_multiple_clients(game_engine):
    """Test multiple web clients connecting"""
    # Arrange
    test_sids = ["client1", "client2", "client3"]
    game_engine.room_state["scene"] = "森林小径"
    
    # Act
    for sid in test_sids:
        await game_engine.on_web_client_connect(sid)
    
    # Assert
    assert game_engine.sio.emit.call_count == len(test_sids)
    
    # Verify each call
    for i, sid in enumerate(test_sids):
        call = game_engine.sio.emit.call_args_list[i]
        assert call[0][0] == 'scene_update'
        assert call[0][1]["name"] == "森林小径"
        assert call[1]["room"] == sid


@pytest.mark.asyncio
async def test_on_web_client_connect_preserves_room_state(game_engine):
    """Test that web client connect doesn't modify room_state"""
    # Arrange
    test_sid = "test_session_preserve"
    original_scene = "黑暗地牢"
    game_engine.room_state = {
        "scene": original_scene,
        "channels": {"player1": "channel1"}
    }
    
    # Act
    await game_engine.on_web_client_connect(test_sid)
    
    # Assert
    assert game_engine.room_state["scene"] == original_scene
    assert "channels" in game_engine.room_state
    assert len(game_engine.room_state["channels"]) == 1


@pytest.mark.asyncio
async def test_on_web_client_connect_with_special_characters(game_engine):
    """Test web client connect with special characters in scene name"""
    # Arrange
    test_sid = "test_session_special"
    game_engine.room_state["scene"] = "🏰 龙之巢穴 <危险> & 神秘"
    
    # Act
    await game_engine.on_web_client_connect(test_sid)
    
    # Assert
    game_engine.sio.emit.assert_called_once()
    args = game_engine.sio.emit.call_args
    assert args[0][1]["name"] == "🏰 龙之巢穴 <危险> & 神秘"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=engine", "--cov-report=html"])
