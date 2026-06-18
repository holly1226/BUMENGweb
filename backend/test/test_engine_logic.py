import os
import sys
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

# ==========================================
# 强制路径注入：直接定位到 backend 文件夹
# ==========================================
current_file = os.path.abspath(__file__)
# backend/test/ -> backend/
backend_dir = os.path.dirname(os.path.dirname(current_file))

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# ==========================================
# 导入测试对象
# ==========================================
try:
    # 既然 backend 已经在 path 里了，直接 import engine 即可
    import engine 
    from engine import GameEngine
except ImportError as e:
    print(f"❌ 导入失败！错误详情: {e}")
    print(f"🔍 正在尝试从目录: {backend_dir} 查找 engine.py")
    print(f"当前 sys.path 内容: {sys.path[:3]}")
    sys.exit(1)

# 导入 discord 用于 spec 校验
try:
    import discord
except ImportError:
    print("❌ 缺少依赖：请运行 'pip install discord.py'")
    sys.exit(1)

class TestGameEngineLogic(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_sio = AsyncMock()
        self.engine = GameEngine(self.mock_bot, self.mock_sio)
        self.engine.manager = AsyncMock()

        # 公共频道模拟
        self.public_channel = AsyncMock(spec=discord.TextChannel)
        self.public_channel.name = "大厅频道"
        self.public_channel.members = [MagicMock(bot=False)] # 补全属性
        
        # 私聊频道模拟
        self.private_channel = AsyncMock(spec=discord.DMChannel)
        self.private_channel.name = "玩家私聊"
        self.private_channel.members = [MagicMock(bot=False)] # 【新增】为测试补全属性

    async def test_1_main_channel_locking(self):
        """测试：主频道一旦锁定，后续操作不会覆盖它"""
        await self.engine.start_lobby(self.public_channel)
        self.assertEqual(self.engine.main_channel, self.public_channel)

        # 即使在私聊中再次触发，main_channel 也不应变
        await self.engine.start_lobby(self.private_channel)
        self.assertEqual(self.engine.main_channel, self.public_channel, "错误：主频道被私聊覆盖了！")

    async def test_2_send_to_public_routing(self):
        """测试：send_to_public 必须发往主频道"""
        await self.engine.start_lobby(self.public_channel)
        self.engine.current_channel = self.private_channel # 模拟当前在私聊
        
        await self.engine.send_to_public("测试公告")
        self.public_channel.send.assert_called_with("测试公告")

if __name__ == "__main__":
    unittest.main()