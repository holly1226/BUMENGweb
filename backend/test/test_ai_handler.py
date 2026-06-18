"本代码用于测试ai_handler"
import asyncio
import os
from dotenv import load_dotenv
import sys

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_handler import get_ai_response

load_dotenv()

async def test_get_ai_response():
    """测试 get_ai_response 函数"""
    
    print("=" * 50)
    print("测试 AI Handler")
    print("=" * 50)
    
    # 测试用例1: 玩家进入房间
    test_cases = [
        {
            "name": "玩家进入房间",
            "user_input": "我推开门走进了房间",
            "historys": "玩家在走廊上,前面有一扇门。"
        },
        {
            "name": "玩家询问线索",
            "user_input": "这个房间有什么可疑的地方吗?",
            "historys": "玩家刚进入房间,看到一张桌子和一把椅子。"
        },
        {
            "name": "玩家尝试检定",
            "user_input": "我想检查桌子的抽屉",
            "historys": "玩家在房间里,面前是一张旧桌子。"
        },
        {
            "name": "玩家获得道具",
            "user_input": "我捡起了地上的钥匙",
            "historys": "玩家在地上发现了一把生锈的钥匙。"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n--- 测试用例 {i}: {test_case['name']} ---")
        print(f"玩家输入: {test_case['user_input']}")
        print(f"历史记录: {test_case['historys']}")
        
        text, json_cmd = await get_ai_response(
            test_case['user_input'],
            test_case['historys']
        )
        
        print(f"\nAI 回复 (文字部分):")
        print(text)
        
        if json_cmd:
            print(f"\nAI 指令 (JSON 部分):")
            print(f"  类型: {json_cmd.get('type')}")
            print(f"  参数: {json_cmd.get('params')}")
        else:
            print(f"\nAI 指令: 无")
        
        print("-" * 50)
    
    print("\n✅ 所有测试完成")

if __name__ == "__main__":
    asyncio.run(test_get_ai_response())
