import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock

# ================= 路径修复逻辑 =================
# 获取当前脚本所在目录 (backend/test)
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取 backend 目录
backend_dir = os.path.dirname(current_dir)
# 将 backend 目录加入系统路径，这样才能直接 import manager 和 engine
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

try:
    from manager import GameManager
    from engine import GameEngine
    print("✅ 模块导入成功：已定位到 manager.py 和 engine.py")
except ImportError as e:
    print(f"❌ 导入失败！请确保你在 TRPGWebDiscord 目录下运行。错误: {e}")
    sys.exit(1)
# ===============================================

async def test_player_signup_flow():
    print("\n" + "="*40)
    print("🧪 开始测试：玩家报名机制 (方案三)")
    print("="*40)

    # 1. 初始化 Mock 环境
    # 我们模拟 Discord 的 bot 和 socket.io，不实际启动网络连接
    mock_bot = MagicMock()
    mock_sio = AsyncMock()
    
    # 实例化 Engine
    engine = GameEngine(mock_bot, mock_sio)
    manager = engine.manager
    
    # 模拟一个 Discord 频道对象
    mock_channel = AsyncMock()
    mock_channel.name = "测试冒险频道"
    # 模拟频道内有很多“潜水”的人，总共 10 个
    mock_channel.members = [MagicMock(bot=False, name=f"潜水员_{i}") for i in range(10)]

    # 2. 测试场景 A：报名流程
    print("\n[步骤 1] 玩家报名测试...")
    
    # 只有 Alice 和 Bob 进行了报名
    await engine.add_player_role_pref("Alice", "擅长火魔法的法师", mock_channel)
    await engine.add_player_role_pref("Bob", "沉默寡言的盾卫", mock_channel)
    
    # 模拟 Alice 多次修改偏好，确保人数不会重复计算
    await engine.add_player_role_pref("Alice", "还是想玩黑客医学生", mock_channel)

    actual_count = len(manager.game_state["players"])
    print(f"📊 报名人数统计：{actual_count}")
    
    assert actual_count == 2, f"❌ 错误：预期报名人数应为 2，实际为 {actual_count}"
    assert "Alice" in manager.game_state["players"]
    assert "Bob" in manager.game_state["players"]
    print("✅ 玩家报名去重逻辑正常。")

    # 3. 测试场景 B：开始游戏与人数锁定
    print("\n[步骤 2] 模拟启动游戏...")
    
    # 填充必要的前置数据
    manager.game_state["suggestions"] = ["赛博朋克", "下雨的深夜"]
    
    # 拦截 manager.start_game，防止它真的去请求 DeepSeek API
    manager.start_game = AsyncMock()
    
    # 触发开始游戏
    await engine.start_game(mock_channel)

    # 获取传给 manager.start_game 的参数
    # call_args[0] 包含了 (prefs_str, role_summary, player_count)
    args = manager.start_game.call_args[0]
    final_prefs = args[0]
    final_role_summary = args[1]
    final_player_count = args[2]

    print(f"🔢 Engine 锁定的最终人数: {final_player_count}")
    print(f"📝 生成的角色汇总内容:\n{final_role_summary}")

    # 核心断言：
    # 虽然频道里有 10 个人，但 final_player_count 必须是 2
    assert final_player_count == 2, f"❌ 错误：Engine 错误地统计了频道总人数 {final_player_count}"
    assert "Alice" in final_role_summary and "Bob" in final_role_summary
    assert "潜水员" not in final_role_summary, "❌ 错误：未报名的潜水员被计入了剧本！"

    print("\n" + "="*40)
    print("🎉 测试通过！方案三显式报名机制运行完美。")
    print("="*40)

if __name__ == "__main__":
    # 运行异步测试
    try:
        asyncio.run(test_player_signup_flow())
    except KeyboardInterrupt:
        pass